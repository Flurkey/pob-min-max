-- Read Path of Building data tables and print one JSON document.
-- This does not launch HeadlessWrapper and does not write into the checkout.
-- Run with cwd = the PoB src/ directory.

local runtime = os.getenv("POB_RUNTIME")
if not runtime or runtime == "" then
	io.stderr:write("POB_RUNTIME is not set\n")
	os.exit(1)
end
package.path = runtime .. "/lua/?.lua;" .. runtime .. "/lua/?/init.lua;" .. package.path

local json = require("dkjson")
bit = bit or require("bit")
-- Data/Global.lua copies its colour table while loading. The checkout defines
-- copyTable in the runtime, which this process does not start.
function copyTable(tbl)
	local out = {}
	for key, value in pairs(tbl) do
		out[key] = value
	end
	return out
end

local function log(message)
	io.stderr:write(message .. "\n")
	io.stderr:flush()
end

local function loadChunk(path)
	local chunk, err = loadfile(path)
	if not chunk then
		error("Could not load " .. path .. ": " .. tostring(err))
	end
	local ok, result = pcall(chunk)
	if not ok then
		error("Could not run " .. path .. ": " .. tostring(result))
	end
	return result
end

local function sanitize(value, seen)
	local kind = type(value)
	if kind == "number" or kind == "string" or kind == "boolean" then
		return value
	end
	if kind ~= "table" then
		return nil
	end
	seen = seen or {}
	if seen[value] then
		error("Game data contains a cycle")
	end
	seen[value] = true
	local out = {}
	for key, item in pairs(value) do
		if (type(key) == "string" or type(key) == "number") and type(item) ~= "function" then
			local cleaned = sanitize(item, seen)
			if cleaned ~= nil then
				out[key] = cleaned
			end
		end
	end
	seen[value] = nil
	return out
end

local function trueKeys(tableValue)
	local names = {}
	if type(tableValue) ~= "table" then
		return names
	end
	for key, on in pairs(tableValue) do
		if on and type(key) == "string" then
			names[#names + 1] = key
		end
	end
	table.sort(names)
	return names
end

local function stringList(tableValue)
	local lines = {}
	if type(tableValue) ~= "table" then
		return lines
	end
	for index = 1, #tableValue do
		if type(tableValue[index]) == "string" then
			lines[#lines + 1] = tableValue[index]
		end
	end
	return lines
end

-- Same file lists Modules/Data.lua passes to LoadModule. Generated.lua and
-- New.lua are not data tables; they build items from the tables loaded here.
local baseFiles = {
	"axe", "bow", "claw", "dagger", "fishing", "mace", "staff", "sword", "wand",
	"helmet", "body", "gloves", "boots", "shield", "quiver", "amulet", "ring",
	"belt", "jewel", "flask", "tincture", "graft",
}
local skillFiles = {
	"act_str", "act_dex", "act_int", "other", "glove", "minion", "spectre",
	"sup_str", "sup_dex", "sup_int",
}
local modFiles = {
	"Data/ModExplicit.lua",
	"Data/ModItemExclusive.lua",
	"Data/ModCorrupted.lua",
	"Data/ModDelve.lua",
	"Data/ModSynthesis.lua",
	"Data/ModScourge.lua",
	"Data/ModEldritch.lua",
	"Data/ModFlask.lua",
	"Data/ModTincture.lua",
	"Data/ModGraft.lua",
	"Data/ModJewel.lua",
	"Data/ModJewelAbyss.lua",
	"Data/ModJewelCluster.lua",
	"Data/ModJewelCharm.lua",
	"Data/ModFoulborn.lua",
	"Data/ModMercenary.lua",
	"Data/Uniques/Special/WatchersEye.lua",
}

log("Loading game version")
dofile("GameVersions.lua")
dofile("Data/Global.lua")
local treeVersion = latestTreeVersion
local treeMeta = treeVersions[treeVersion]
if not treeMeta then
	error("GameVersions.lua has no entry for " .. tostring(treeVersion))
end

local skillTypeById = {}
for name, id in pairs(SkillType) do
	skillTypeById[id] = name
end

local function namedSkillTypes(set)
	local names = {}
	if type(set) ~= "table" then
		return names
	end
	for id, on in pairs(set) do
		if on then
			names[#names + 1] = skillTypeById[id] or tostring(id)
		end
	end
	table.sort(names)
	return names
end

local function makeSkillMod(modName, modType, modVal, ...)
	return { name = modName, type = modType, value = modVal }
end
local function makeFlagMod(modName, ...)
	return makeSkillMod(modName, "FLAG", true, ...)
end
local function makeSkillDataMod(dataKey, dataValue, ...)
	return makeSkillMod("SkillData", "LIST", { key = dataKey, value = dataValue }, ...)
end

log("Loading item bases")
local bases = {}
local baseNames = {}
for _, kind in ipairs(baseFiles) do
	local path = "Data/Bases/" .. kind .. ".lua"
	local loader = loadChunk(path)
	if type(loader) ~= "function" then
		error(path .. " did not return a base loader")
	end
	local itemBases = {}
	loader(itemBases)
	for name, base in pairs(itemBases) do
		if type(name) ~= "string" or type(base) ~= "table" then
			error("Bad item base in " .. path)
		end
		if baseNames[name] then
			error("Duplicate item base '" .. name .. "' in " .. path)
		end
		baseNames[name] = true
		local req = {}
		if type(base.req) == "table" then
			for _, stat in ipairs({ "level", "str", "dex", "int" }) do
				if type(base.req[stat]) == "number" then
					req[stat] = base.req[stat]
				end
			end
		end
		-- An empty Lua table encodes as a JSON array. Requirements are an object.
		if next(req) == nil then
			setmetatable(req, { __jsontype = "object" })
		end
		local record = {
			name = name,
			sourcePath = path,
			itemType = base.type,
			tags = trueKeys(base.tags),
			req = req,
			hidden = base.hidden and true or false,
		}
		if type(base.subType) == "string" then record.subType = base.subType end
		if type(base.implicit) == "string" then record.implicit = base.implicit end
		if type(base.socketLimit) == "number" then record.socketLimit = base.socketLimit end
		if type(base.armour) == "table" then record.armour = sanitize(base.armour) end
		if type(base.weapon) == "table" then record.weapon = sanitize(base.weapon) end
		if type(base.flask) == "table" then record.flask = sanitize(base.flask) end
		if type(base.tincture) == "table" then record.tincture = sanitize(base.tincture) end
		bases[#bases + 1] = record
	end
end

local function parseUnique(raw, category, sourcePath)
	if type(raw) ~= "string" or raw == "" then
		error("Unique entry in " .. sourcePath .. " is empty")
	end
	local name, baseName = raw:match("^([^\n]+)\n([^\n]+)")
	if not name or not baseName then
		error("Unique entry in " .. sourcePath .. " has no name and base")
	end
	return {
		name = name,
		baseName = baseName,
		category = category,
		sourcePath = sourcePath,
		rawText = raw,
	}
end

log("Loading unique items")
local uniques = {}
local function loadUniques(path, category)
	local list = loadChunk(path)
	if type(list) ~= "table" then
		error(path .. " did not return a unique list")
	end
	for _, raw in ipairs(list) do
		uniques[#uniques + 1] = parseUnique(raw, category, path)
	end
end
for _, kind in ipairs(baseFiles) do
	loadUniques("Data/Uniques/" .. kind .. ".lua", kind)
end
loadUniques("Data/Uniques/Special/race.lua", "race")

log("Loading item mods")
local mods = {}
for _, path in ipairs(modFiles) do
	local loaded = loadChunk(path)
	if type(loaded) ~= "table" then
		error(path .. " did not return a mod table")
	end
	for modId, mod in pairs(loaded) do
		if type(mod) == "table" then
			local lines = stringList(mod)
			local record = {
				modId = tostring(modId),
				sourcePath = path,
				lines = lines,
				modTags = stringList(mod.modTags),
			}
			if type(mod.type) == "string" then record.modType = mod.type end
			if type(mod.affix) == "string" then record.affix = mod.affix end
			if type(mod.group) == "string" then record.group = mod.group end
			if type(mod.level) == "number" then record.level = mod.level end
			if #lines > 0 or record.affix or record.modType then
				mods[#mods + 1] = record
			end
		end
	end
end

log("Loading skill gems")
local skills = {}
local skillPaths = {}
for _, kind in ipairs(skillFiles) do
	local path = "Data/Skills/" .. kind .. ".lua"
	log("  " .. path)
	local loader = loadChunk(path)
	if type(loader) ~= "function" then
		error(path .. " did not return a skill loader")
	end
	loader(skills, makeSkillMod, makeFlagMod, makeSkillDataMod)
	for skillId in pairs(skills) do
		if not skillPaths[skillId] then
			skillPaths[skillId] = path
		end
	end
end

local function reshapeLevel(index, row)
	if type(row) ~= "table" then
		error("Skill level " .. tostring(index) .. " is not a table")
	end
	local values = {}
	for position = 1, #row do
		local item = row[position]
		if type(item) ~= "function" then
			values[#values + 1] = sanitize(item)
		end
	end
	local out = { level = index, values = values }
	for key, item in pairs(row) do
		if type(key) == "string" and type(item) ~= "function" then
			out[key] = sanitize(item)
		end
	end
	return out
end

local function grantedEffect(skillId)
	local skill = skills[skillId]
	if not skill then
		return nil
	end
	local levels = {}
	if type(skill.levels) == "table" then
		local indexes = {}
		for key in pairs(skill.levels) do
			if type(key) == "number" then
				indexes[#indexes + 1] = key
			end
		end
		table.sort(indexes)
		for _, index in ipairs(indexes) do
			levels[#levels + 1] = reshapeLevel(index, skill.levels[index])
		end
	end
	local effect = {
		id = skillId,
		name = skill.name,
		support = skill.support and true or false,
		skillTypes = namedSkillTypes(skill.skillTypes),
		requireSkillTypes = namedSkillTypes(skill.requireSkillTypes),
		addSkillTypes = namedSkillTypes(skill.addSkillTypes),
		excludeSkillTypes = namedSkillTypes(skill.excludeSkillTypes),
		weaponTypes = trueKeys(skill.weaponTypes),
		stats = stringList(skill.stats),
		constantStats = sanitize(skill.constantStats) or {},
		qualityStats = sanitize(skill.qualityStats) or {},
		baseFlags = trueKeys(skill.baseFlags),
		levels = levels,
		sourcePath = skillPaths[skillId],
	}
	if type(skill.description) == "string" then effect.description = skill.description end
	if type(skill.color) == "number" then effect.color = skill.color end
	if type(skill.castTime) == "number" then effect.castTime = skill.castTime end
	return effect
end

local gemTable = loadChunk("Data/Gems.lua")
if type(gemTable) ~= "table" then
	error("Data/Gems.lua did not return a gem table")
end
local gems = {}
for gemId, gem in pairs(gemTable) do
	if type(gemId) ~= "string" or type(gem) ~= "table" then
		error("Bad gem entry in Data/Gems.lua")
	end
	local effect = grantedEffect(gem.grantedEffectId)
	if not effect then
		error("Gem " .. gemId .. " grants missing skill " .. tostring(gem.grantedEffectId))
	end
	local record = {
		id = gemId,
		name = gem.name,
		gameId = gem.gameId,
		variantId = gem.variantId,
		grantedEffectId = gem.grantedEffectId,
		tags = trueKeys(gem.tags),
		tagString = gem.tagString,
		reqStr = gem.reqStr or 0,
		reqDex = gem.reqDex or 0,
		reqInt = gem.reqInt or 0,
		vaalGem = gem.vaalGem and true or false,
		sourcePath = "Data/Gems.lua",
		grantedEffect = effect,
	}
	if type(gem.baseTypeName) == "string" then record.baseTypeName = gem.baseTypeName end
	if type(gem.naturalMaxLevel) == "number" then record.naturalMaxLevel = gem.naturalMaxLevel end
	if type(gem.secondaryGrantedEffectId) == "string" then
		local secondary = grantedEffect(gem.secondaryGrantedEffectId)
		if not secondary then
			error("Gem " .. gemId .. " secondary skill is missing: " .. gem.secondaryGrantedEffectId)
		end
		record.secondaryGrantedEffectId = gem.secondaryGrantedEffectId
		record.secondaryGrantedEffect = secondary
	end
	gems[#gems + 1] = record
end

log("Loading passive tree " .. treeVersion)
local tree = loadChunk("TreeData/" .. treeVersion .. "/tree.lua")
if type(tree) ~= "table" or type(tree.nodes) ~= "table" or type(tree.groups) ~= "table" then
	error("TreeData/" .. treeVersion .. "/tree.lua has no nodes")
end
if type(tree.points) ~= "table" or type(tree.points.totalPoints) ~= "number" or type(tree.points.ascendancyPoints) ~= "number" then
	error("Passive tree has no point budget")
end

local function playable(node)
	if type(node) ~= "table" or node.group == nil then
		return false
	end
	local group = tree.groups[node.group]
	if type(group) ~= "table" or group.isProxy or node.isProxy then
		return false
	end
	if type(node.expansionJewel) == "table" and node.expansionJewel.parent then
		return false
	end
	return true
end

local function nodeTypeOf(node)
	if node.classStartIndex ~= nil then return "ClassStart" end
	if node.isAscendancyStart then return "AscendClassStart" end
	if node.isMastery or node.m then return "Mastery" end
	if node.isJewelSocket then return "Socket" end
	if node.isKeystone or node.ks then return "Keystone" end
	if node.isNotable or node["not"] then return "Notable" end
	return "Normal"
end

local function numericIds(list)
	local ids = {}
	if type(list) ~= "table" then
		return ids
	end
	for index = 1, #list do
		local id = tonumber(list[index])
		if id then
			ids[#ids + 1] = id
		end
	end
	return ids
end

local treePath = "TreeData/" .. treeVersion .. "/tree.lua"
local nodes = {}
local playableIds = {}
for key, node in pairs(tree.nodes) do
	local id = type(node) == "table" and (tonumber(node.skill) or tonumber(key)) or nil
	if id and playable(node) then
		if playableIds[id] then
			error("Duplicate passive node " .. tostring(id))
		end
		playableIds[id] = true
		local record = {
			id = id,
			name = type(node.name) == "string" and node.name or "",
			nodeType = nodeTypeOf(node),
			stats = stringList(node.stats),
			grantedPassivePoints = tonumber(node.grantedPassivePoints) or 0,
			multipleChoice = node.isMultipleChoice and true or false,
			multipleChoiceOption = node.isMultipleChoiceOption and true or false,
			sourcePath = treePath,
		}
		if type(node.ascendancyName) == "string" then
			record.ascendancyName = node.ascendancyName
		end
		if node.classStartIndex ~= nil then
			record.classStartIndex = node.classStartIndex
		end
		nodes[#nodes + 1] = record
	end
end

local classes = {}
for index, class in ipairs(tree.classes or {}) do
	local ascendancies = {}
	for _, ascendancy in ipairs(class.ascendancies or class.classes or {}) do
		if type(ascendancy) == "table" and type(ascendancy.name) == "string" then
			ascendancies[#ascendancies + 1] = {
				id = ascendancy.id or ascendancy.name,
				name = ascendancy.name,
			}
		end
	end
	classes[#classes + 1] = {
		index = index - 1,
		name = class.name,
		baseStr = class.base_str,
		baseDex = class.base_dex,
		baseInt = class.base_int,
		ascendancies = ascendancies,
	}
end

local alternates = {}
if type(tree.alternate_ascendancies) == "table" then
	for _, ascendancy in ipairs(tree.alternate_ascendancies) do
		if type(ascendancy) == "table" and type(ascendancy.name) == "string" then
			alternates[#alternates + 1] = {
				id = ascendancy.id or ascendancy.name,
				name = ascendancy.name,
			}
		end
	end
end

local function assignStart(list, ascendancyName, nodeId)
	for _, ascendancy in ipairs(list) do
		if ascendancy.id == ascendancyName then
			if ascendancy.startNodeId and ascendancy.startNodeId ~= nodeId then
				error("Ascendancy " .. ascendancyName .. " has two start nodes")
			end
			ascendancy.startNodeId = nodeId
			return true
		end
	end
	return false
end
for _, node in ipairs(nodes) do
	if node.nodeType == "AscendClassStart" then
		local found = false
		for _, class in ipairs(classes) do
			if assignStart(class.ascendancies, node.ascendancyName, node.id) then
				found = true
			end
		end
		if assignStart(alternates, node.ascendancyName, node.id) then
			found = true
		end
		if not found then
			error("Ascendancy start " .. tostring(node.id) .. " has no class entry for " .. tostring(node.ascendancyName))
		end
	end
end

local edgeSeen = {}
local edges = {}
local function addEdge(left, right)
	if not left or not right or left == right then
		return
	end
	if not playableIds[left] or not playableIds[right] then
		return
	end
	local lo, hi = left, right
	if lo > hi then lo, hi = hi, lo end
	local key = lo .. ":" .. hi
	if edgeSeen[key] then
		return
	end
	edgeSeen[key] = true
	edges[#edges + 1] = { lo, hi }
end
for key, node in pairs(tree.nodes) do
	local id = type(node) == "table" and (tonumber(node.skill) or tonumber(key)) or nil
	if id and playableIds[id] then
		for _, other in ipairs(numericIds(node.out)) do
			addEdge(id, other)
		end
		for _, other in ipairs(numericIds(node["in"])) do
			addEdge(id, other)
		end
	end
end

local document = {
	treeVersion = treeVersion,
	treeDisplay = treeMeta.display,
	points = {
		total = tree.points.totalPoints,
		ascendancy = tree.points.ascendancyPoints,
	},
	bases = bases,
	uniques = uniques,
	mods = mods,
	gems = gems,
	classes = classes,
	alternateAscendancies = alternates,
	nodes = nodes,
	edges = edges,
}
log(string.format(
	"Encoding JSON (%d bases, %d uniques, %d mods, %d gems, %d nodes, %d edges)",
	#bases, #uniques, #mods, #gems, #nodes, #edges
))
io.write(json.encode(document))
io.write("\n")
