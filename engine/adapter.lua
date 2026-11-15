-- Headless driver for an unmodified PathOfBuildingCommunity checkout.
-- Working directory must be the PoB src/ directory.
-- Speaks one JSON object per line on stdin/stdout. Diagnostics go to stderr.

local function env(name, fallback)
	local value = os.getenv(name)
	if value and value ~= "" then
		return value
	end
	return fallback
end

local POB_SRC = env("POB_SRC", ".")
local POB_RUNTIME = env("POB_RUNTIME")
local POB_USER = env("POB_USER", "/tmp/pob-user")
local UTF8_DIR = env("POB_UTF8_DIR", "/tmp/luautf8")

if not POB_RUNTIME then
	io.stderr:write("POB_RUNTIME is required\n")
	os.exit(1)
end

bit = require("bit")
package.path = POB_RUNTIME .. "/lua/?.lua;" .. POB_RUNTIME .. "/lua/?/init.lua;" .. package.path
package.cpath = UTF8_DIR .. "/?.so;" .. package.cpath

local function read_source(path)
	local file, openErr = io.open(path, "rb")
	if not file then
		return nil, openErr or ("cannot open " .. tostring(path))
	end
	local source = file:read("*a")
	file:close()
	if source:sub(1, 1) == "#" then
		-- PoB launcher files start with #@. Current LuaJIT does not treat that as a comment.
		source = "--" .. source:sub(2)
	end
	return source
end

local raw_loadfile = loadfile
function loadfile(path, ...)
	if path == nil then
		return raw_loadfile()
	end
	local source, err = read_source(path)
	if not source then
		return nil, err
	end
	return load(source, "@" .. path)
end

function dofile(path)
	if path == nil then
		error("dofile(nil) is not used")
	end
	local chunk, err = loadfile(path)
	if not chunk then
		error(err)
	end
	return chunk()
end

function print(...)
	local count = select("#", ...)
	local parts = {}
	for index = 1, count do
		parts[index] = tostring(select(index, ...))
	end
	io.stderr:write(table.concat(parts, "\t"), "\n")
end

local graphic_loaded = false
local raw_dofile = dofile
function dofile(path)
	local result = raw_dofile(path)
	if not graphic_loaded and type(path) == "string" and path:find("_SimpleGraphic", 1, true) then
		graphic_loaded = true
		local started = os.clock()
		function GetScriptPath()
			return POB_SRC
		end
		function GetRuntimePath()
			return POB_RUNTIME
		end
		function GetUserPath()
			return POB_USER
		end
		function GetWorkDir()
			return POB_SRC
		end
		function GetTime()
			return math.floor((os.clock() - started) * 1000)
		end
		function MakeDir(path)
			os.execute("mkdir -p " .. string.format("%q", path))
			return true
		end
		function ConPrintf(fmt, ...)
			io.stderr:write(string.format(fmt, ...), "\n")
		end
		-- Real zlib inflate. The stock headless stub returns "" and would
		-- discard compressed jewel data.
		local ok, inflateErr = pcall(function()
			local ffi = require("ffi")
			ffi.cdef[[
				int uncompress(uint8_t *dest, unsigned long *destLen, const uint8_t *source, unsigned long sourceLen);
			]]
			local zlib = ffi.load("z")
			function Inflate(data)
				if not data or #data == 0 then
					return ""
				end
				local size = math.max(#data * 4, 65536)
				while size <= 64 * 1024 * 1024 do
					local buf = ffi.new("uint8_t[?]", size)
					local len = ffi.new("unsigned long[1]", size)
					local rc = zlib.uncompress(buf, len, data, #data)
					if rc == 0 then
						return ffi.string(buf, len[0])
					end
					if rc ~= -5 then
						return ""
					end
					size = size * 2
				end
				return ""
			end
		end)
		if not ok then
			io.stderr:write("inflate unavailable: " .. tostring(inflateErr) .. "\n")
		end
	end
	return result
end

local bootOk, bootErr = pcall(function()
	dofile("HeadlessWrapper.lua")
end)
if not bootOk then
	io.stderr:write("engine boot failed: " .. tostring(bootErr) .. "\n")
	os.exit(1)
end

if launch and launch.main then
	launch.main.disableDevAutoSave = true
	launch.main.userPath = POB_USER .. "/"
	launch.main.defaultBuildPath = POB_USER .. "/Builds/"
	launch.main.buildPath = launch.main.defaultBuildPath
	MakeDir(launch.main.buildPath)
end
os.execute(string.format("rmdir %q >/dev/null 2>&1", POB_SRC .. "/Builds"))

if launch and launch.promptMsg then
	io.stderr:write("engine prompt: " .. tostring(launch.promptMsg) .. "\n")
	os.exit(1)
end

if not build or not build.calcsTab then
	io.stderr:write("engine booted without a build\n")
	os.exit(1)
end

local json = require("dkjson")

local function numeric_stats(output)
	local stats = {}
	if type(output) ~= "table" then
		return stats
	end
	for key, value in pairs(output) do
		if type(key) == "string" and type(value) == "number" and value == value and value ~= math.huge and value ~= -math.huge then
			stats[key] = value
		end
	end
	return stats
end

local function recalculate()
	-- Always run the calculation modules. Stored XML PlayerStat values are never read.
	wipeGlobalCache()
	build.outputRevision = (build.outputRevision or 0) + 1
	build.buildFlag = false
	if build.skillsTab and build.skillsTab.UpdateSocketGroups then
		build.skillsTab:UpdateSocketGroups()
	end
	build.calcsTab:BuildOutput()
	-- The desktop frame estimates level from allocated points when auto-level is on.
	-- Do that here, then calculate once more if the level changed, so a headless
	-- result matches the build the GUI would settle on.
	if build.characterLevelAutoMode and build.EstimatePlayerProgress then
		local levelBefore = build.characterLevel
		build:EstimatePlayerProgress()
		if build.characterLevel ~= levelBefore then
			build.configTab:BuildModList()
			build.calcsTab:BuildOutput()
		end
	end
	local output = build.calcsTab.mainOutput
	if type(output) ~= "table" then
		error("calculation produced no mainOutput")
	end
	return {
		source = "pob-engine",
		ignoredStoredPlayerStat = true,
		outputRevision = build.outputRevision,
		level = build.characterLevel,
		treeVersion = build.spec and build.spec.treeVersion or nil,
		stats = numeric_stats(output),
	}
end

local function engine_info()
	local treeVersion = latestTreeVersion
	local treeDisplay = treeVersions and treeVersions[treeVersion] and treeVersions[treeVersion].display or nil
	local spec = build and build.spec or nil
	return {
		versionNumber = launch and launch.versionNumber or nil,
		versionBranch = launch and launch.versionBranch or nil,
		devMode = launch and launch.devMode or false,
		engineRevision = env("POB_ENGINE_REVISION", "unknown"),
		engineCommitTime = env("POB_ENGINE_COMMIT_TIME", ""),
		latestTreeVersion = treeVersion,
		latestTreeDisplay = treeDisplay,
		buildTreeVersion = spec and spec.treeVersion or nil,
		buildTreeDisplay = spec and spec.treeVersion and treeVersions[spec.treeVersion] and treeVersions[spec.treeVersion].display or nil,
		className = spec and spec.curClassName or nil,
		ascendClassName = spec and spec.curAscendClassName or nil,
		level = build and build.characterLevel or nil,
	}
end

local function clear_prompt()
	if launch then
		launch.promptMsg = nil
	end
	local main = launch and launch.main
	if main and main.ClosePopup and main.popups then
		while #main.popups > 0 do
			main:ClosePopup()
		end
	end
end

local function startup_error()
	if launch and launch.promptMsg then
		return tostring(launch.promptMsg)
	end
	return nil
end

local function import_xml(xmlText, name)
	if type(xmlText) ~= "string" or xmlText == "" then
		error("xml is required")
	end
	-- A previous failed load leaves promptMsg set, and PoB will not replace it.
	clear_prompt()
	loadBuildFromXML(xmlText, name or "imported")
	local err = startup_error()
	if err then
		clear_prompt()
		error(err)
	end
	if launch and launch.main then
		launch.main.disableDevAutoSave = true
	end
	build = _G.build
	if not build or not build.calcsTab then
		error("import did not leave a build loaded")
	end
	return engine_info()
end

local function equip_item(text, slotName)
	if type(text) ~= "string" or text == "" then
		error("item text is required")
	end
	local item = new("Item"):Item(text)
	if not item.base then
		error("PoB did not recognise an item base in the text")
	end
	build.itemsTab:AddItem(item, true)
	local slot = slotName or item:GetPrimarySlot()
	local control = build.itemsTab.slots[slot]
	if not control then
		error("unknown equipment slot: " .. tostring(slot))
	end
	if not build.itemsTab:IsItemValidForSlot(item, slot) then
		error("item is not valid for slot " .. slot)
	end
	control:SetSelItemId(item.id)
	build.itemsTab:PopulateSlots()
	build.buildFlag = true
	local parsed = {}
	for _, line in ipairs(item.explicitModLines or {}) do
		parsed[#parsed + 1] = line.line or line
	end
	return {
		id = item.id,
		name = item.name,
		baseName = item.baseName,
		slot = slot,
		rarity = item.rarity,
		explicitLines = parsed,
	}
end

local function node_text(node)
	local parts = {}
	for _, line in ipairs(node.sd or {}) do
		parts[#parts + 1] = tostring(line)
	end
	return table.concat(parts, "\n")
end

local function find_life_node()
	local spec = build.spec
	local best
	for _, node in pairs(spec.nodes) do
		if not node.alloc and node.path and #node.path > 1 and node.type ~= "ClassStart" and node.type ~= "AscendClassStart" and node.type ~= "Mastery" and not node.ascendancyName and not node.isJewelSocket then
			local text = node_text(node):lower()
			local grantsLife = text:find("maximum life", 1, true) and not text:find("minion", 1, true) and not text:find("reduced", 1, true) and not text:find("reserved", 1, true)
			-- pairs() order is not stable. Shortest path, then lowest id.
			if grantsLife and (not best or #node.path < #best.path or (#node.path == #best.path and node.id < best.id)) then
				best = node
			end
		end
	end
	if not best then
		error("no connected maximum-life passive was found on the loaded tree")
	end
	return best
end

local function allocate_node(nodeId)
	local spec = build.spec
	local node
	if nodeId ~= nil then
		node = spec.nodes[nodeId]
		if not node then
			error("passive node was not found: " .. tostring(nodeId))
		end
	else
		node = find_life_node()
	end
	if not node then
		error("passive node was not found: " .. tostring(nodeId))
	end
	if not node.path then
		error("passive node has no path from the class start: " .. tostring(node.id))
	end
	local before = spec:CountAllocNodes()
	local pathLength = node.path and #node.path or 0
	spec:AllocNode(node)
	build.buildFlag = true
	local after = spec:CountAllocNodes()
	return {
		id = node.id,
		name = node.name,
		text = node_text(node),
		pathLength = pathLength,
		allocatedBefore = before,
		allocatedAfter = after,
	}
end

local function export_xml()
	-- SaveDB writes PlayerStat from the live calculation output. Callers must
	-- still recalculate after a later import; those tags are a cache.
	recalculate()
	local xmlText = build:SaveDB("export")
	if type(xmlText) ~= "string" or not xmlText:find("<PathOfBuilding", 1, true) then
		error("export did not produce PathOfBuilding XML")
	end
	return { xml = xmlText }
end

local function build_summary()
	local info = engine_info()
	local used = build.spec:CountAllocNodes()
	local items = {}
	for slotName, slot in pairs(build.itemsTab.slots) do
		if not slot.nodeId and slot.selItemId and slot.selItemId ~= 0 then
			local item = build.itemsTab.items[slot.selItemId]
			if item then
				items[#items + 1] = { slot = slotName, name = item.name, baseName = item.baseName, id = item.id }
			end
		end
	end
	table.sort(items, function(a, b) return a.slot < b.slot end)
	info.allocatedPoints = used
	info.equipped = items
	return info
end

local actions = {
	health = function()
		return engine_info()
	end,
	summary = function()
		return build_summary()
	end,
	import_xml = function(request)
		return import_xml(request.xml, request.name)
	end,
	calculate = function()
		return recalculate()
	end,
	equip_item = function(request)
		return equip_item(request.text, request.slot)
	end,
	allocate_node = function(request)
		return allocate_node(request.nodeId)
	end,
	export_xml = function()
		return export_xml()
	end,
}

local function clean_error(err)
	local text = tostring(err)
	text = text:gsub("%^x%x%x%x%x%x%x", "")
	text = text:gsub("%^%d", "")
	text = text:gsub("%^%*", "")
	text = text:gsub("\n+", " "):gsub("%s+", " ")
	text = text:gsub("^%S+:%d+:%s*", "")
	text = text:gsub("Press Enter/Escape.*", "")
	return (text:gsub("%s+$", ""))
end

local function reply(id, ok, result, err)
	local payload = { id = id, ok = ok }
	if ok then
		payload.result = result
	else
		payload.error = clean_error(err)
	end
	io.stdout:write(json.encode(payload), "\n")
	io.stdout:flush()
end

io.stdout:write(json.encode({ ok = true, ready = true, result = engine_info() }), "\n")
io.stdout:flush()

for line in io.lines() do
	if line:match("%S") then
		local decoded, _, err = json.decode(line)
		if not decoded then
			reply(nil, false, nil, err or "invalid json")
		else
			local action = actions[decoded.action]
			if not action then
				reply(decoded.id, false, nil, "unknown action: " .. tostring(decoded.action))
			else
				local ok, value = pcall(action, decoded)
				if ok then
					reply(decoded.id, true, value, nil)
				else
					reply(decoded.id, false, nil, value)
				end
			end
		end
	end
end
