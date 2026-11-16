"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { StatTable } from "@/components/stat-table";
import { api } from "@/lib/api";
import { formatDelta, formatStat, formatWhen, revisionLabel } from "@/lib/format";
import type { Comparison, EngineInfo, Inspection, LibraryBuild, Revision } from "@/lib/types";

type View = Inspection;

export default function Page() {
  const [engine, setEngine] = useState<EngineInfo | null>(null);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [builds, setBuilds] = useState<LibraryBuild[]>([]);
  const [query, setQuery] = useState("");
  const [history, setHistory] = useState<Revision[]>([]);
  const [view, setView] = useState<View | null>(null);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [xml, setXml] = useState<string | null>(null);
  const [importName, setImportName] = useState("Imported build");
  const [importXml, setImportXml] = useState("");
  const [cacheNote, setCacheNote] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<EngineInfo>("/api/engine")
      .then(setEngine)
      .catch((reason: Error) => setEngineError(reason.message));
    refreshLibrary("").catch((reason: Error) => setEngineError(reason.message));
  }, []);

  async function refreshLibrary(nextQuery: string) {
    const payload = await api<{ builds: LibraryBuild[]; storage: string }>(
      `/api/library?q=${encodeURIComponent(nextQuery)}`,
    );
    if (payload.storage !== "sqlite") {
      throw new Error("The build library is not the local SQLite store.");
    }
    setBuilds(payload.builds);
    return payload.builds;
  }

  async function refreshHistory(buildId: string) {
    const payload = await api<{ build: LibraryBuild; revisions: Revision[] }>(`/api/library/${buildId}`);
    setHistory(payload.revisions);
    return payload;
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  function showInspection(inspection: View, message: string) {
    if (inspection.calculation.source !== "pob-engine" || inspection.summary.source !== "pob-engine") {
      throw new Error("The response did not come from the Path of Building engine.");
    }
    setView({
      ...inspection,
      saved: inspection.revision.id === inspection.build.savedRevisionId,
    });
    setXml(null);
    setComparison(null);
    setNote(message);
  }

  async function openBuild(build: LibraryBuild) {
    const payload = await refreshHistory(build.id);
    const revisionId = build.savedRevisionId ?? payload.revisions.at(-1)?.id;
    if (!revisionId) throw new Error("This build has no revisions.");
    const inspection = await api<Inspection>(`/api/builds/${revisionId}/inspect`, { method: "POST" });
    showInspection(inspection, `Opened the stored revision of ${build.name}.`);
    setCacheNote(null);
    setLeftId(build.savedRevisionId ?? "");
    setRightId("");
  }

  async function openRevision(revisionId: string) {
    const inspection = await api<Inspection>(`/api/builds/${revisionId}/inspect`, { method: "POST" });
    showInspection(
      inspection,
      inspection.saved ? "Showing the stored build." : "Showing a working copy. The stored build is unchanged.",
    );
  }

  async function importText(name: string, xmlText: string, message: string, cache: string | null) {
    const imported = await api<Inspection & { info: unknown }>("/api/builds", {
      method: "POST",
      body: JSON.stringify({ name, xml: xmlText }),
    });
    await refreshLibrary(query);
    await refreshHistory(imported.build.id);
    setCacheNote(cache);
    setLeftId(imported.build.savedRevisionId ?? imported.revision.id);
    setRightId("");
    showInspection(imported, message);
  }

  const savedId = view?.build.savedRevisionId ?? "";
  const isStored = view ? view.revision.id === savedId : false;
  const isDraft = view?.revision.status === "draft";
  const revisionState = !view ? "" : isStored ? "Stored build" : isDraft ? "Working copy" : "Earlier revision";

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header className="flex flex-col gap-2">
        <p className="text-xs uppercase tracking-[0.2em] text-muted">Phase 2</p>
        <h1 className="text-3xl font-semibold">PoE Forge</h1>
        <p className="max-w-3xl text-sm text-muted">
          Builds live in a local SQLite library. Stats come from the running Path of Building engine. Edits are stored
          as working copies until you save.
        </p>
      </header>

      <section className="rounded-lg border border-border bg-card p-4" data-testid="engine-panel">
        <h2 className="text-sm font-medium">Engine</h2>
        {engineError ? (
          <p className="mt-2 text-sm text-danger" role="alert">
            {engineError}. Start the engine service, then reload.
          </p>
        ) : engine ? (
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
            <div className="min-w-0">
              <dt className="text-muted">Revision</dt>
              <dd className="break-all font-mono text-xs" data-testid="engine-revision">
                {engine.engineRevision}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Matches pin</dt>
              <dd>{engine.revisionMatchesPin ? "yes" : "no"}</dd>
            </div>
            <div>
              <dt className="text-muted">Manifest</dt>
              <dd>{engine.versionNumber}</dd>
            </div>
            <div>
              <dt className="text-muted">Skill tree</dt>
              <dd>
                {engine.latestTreeDisplay} ({engine.latestTreeVersion})
              </dd>
            </div>
          </dl>
        ) : (
          <p className="mt-2 text-sm text-muted">Connecting…</p>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <section className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4">
          <div>
            <h2 className="text-sm font-medium">Library</h2>
            <p className="mt-1 text-xs text-muted">SQLite on this machine. Path of Building save files are not read.</p>
          </div>
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              run(() => refreshLibrary(query).then(() => undefined));
            }}
          >
            <label className="sr-only" htmlFor="library-search">
              Search builds
            </label>
            <input
              id="library-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search names"
              className="h-9 min-w-0 flex-1 rounded-md border border-border bg-background px-3 text-sm"
            />
            <Button type="submit" variant="secondary" size="sm" disabled={busy}>
              Search
            </Button>
          </form>
          <ul className="flex flex-col gap-1" data-testid="library-list">
            {builds.length === 0 ? <li className="text-sm text-muted">No builds stored yet.</li> : null}
            {builds.map((build) => {
              const selected = view?.build.id === build.id;
              return (
                <li key={build.id}>
                  <button
                    type="button"
                    data-testid="library-build"
                    className={`w-full rounded-md px-2 py-2 text-left text-sm hover:bg-white/5 ${selected ? "bg-white/10" : ""}`}
                    onClick={() => run(() => openBuild(build))}
                    disabled={busy}
                  >
                    <span className="block font-medium">{build.name}</span>
                    <span className="block text-xs text-muted">
                      {revisionLabel(build.savedLabel ?? "saved")} · {formatWhen(build.updatedAt)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="flex flex-col gap-2 border-t border-border pt-3">
            <Button
              disabled={busy || !engine}
              onClick={() =>
                run(async () => {
                  const file = await api<{ name: string; xml: string }>("/api/fixtures/scion-baseline");
                  await importText(file.name, file.xml, "Imported the engine-exported Scion baseline.", null);
                })
              }
            >
              Import baseline
            </Button>
            <Button
              variant="secondary"
              disabled={busy || !engine}
              onClick={() =>
                run(async () => {
                  const file = await api<{ xml: string }>("/api/fixtures/scion-baseline");
                  const forged = file.xml.replace('stat="Life" value="60"', 'stat="Life" value="999999"');
                  await importText(
                    "Forged cache",
                    forged,
                    "Imported a separate copy whose stored Life cache is 999999.",
                    "Imported XML Life cache: 999999. The table below is the engine calculation.",
                  );
                })
              }
            >
              Import forged Life cache
            </Button>
            <label className="text-xs text-muted" htmlFor="import-name">
              Import XML
            </label>
            <input
              id="import-name"
              value={importName}
              onChange={(event) => setImportName(event.target.value)}
              className="h-9 rounded-md border border-border bg-background px-3 text-sm"
            />
            <textarea
              value={importXml}
              onChange={(event) => setImportXml(event.target.value)}
              placeholder="Paste Path of Building XML"
              className="h-24 rounded-md border border-border bg-background p-2 font-mono text-xs"
            />
            <input
              type="file"
              accept=".xml,text/xml"
              aria-label="Build XML file"
              className="text-xs text-muted"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                file.text().then((text) => {
                  setImportName(file.name.replace(/\.xml$/i, ""));
                  setImportXml(text);
                });
              }}
            />
            <Button
              variant="secondary"
              disabled={busy || !engine || importXml.trim() === "" || importName.trim() === ""}
              onClick={() => run(() => importText(importName.trim(), importXml, `Imported ${importName.trim()}.`, null))}
            >
              Import into library
            </Button>
          </div>
        </section>

        <div className="flex flex-col gap-6">
          {view ? (
            <section className="rounded-lg border border-border bg-card p-4" data-testid="inspector">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-medium">{view.build.name}</h2>
                  <p className="mt-1 text-sm text-muted">
                    {view.summary.className ?? "Unknown class"}
                    {view.summary.ascendClassName && view.summary.ascendClassName !== "None"
                      ? ` · ${view.summary.ascendClassName}`
                      : ""}
                    {" · level "}
                    {view.calculation.level ?? view.summary.level ?? "—"}
                    {" · tree "}
                    {view.summary.treeDisplay ?? view.calculation.treeVersion ?? "—"}
                    {" · points "}
                    {view.summary.allocatedPoints ?? "—"}
                  </p>
                </div>
                <p className="rounded-full border border-border px-3 py-1 text-xs" data-testid="revision-state">
                  {revisionState}
                </p>
              </div>
              {isDraft ? (
                <p className="mt-3 text-sm" data-testid="working-copy-banner">
                  This is a working copy. The stored build stays as it is until you save.
                </p>
              ) : null}
              {cacheNote ? <p className="mt-3 text-sm text-muted">{cacheNote}</p> : null}
              <p className="mt-3 font-mono text-xs text-muted" data-testid="calc-source">
                {view.calculation.source} · {view.calculation.engineRevision} · manifest {view.calculation.manifestVersion}
              </p>
              <div className="mt-4">
                <StatTable stats={view.calculation.stats} />
              </div>
              <div className="mt-4">
                <h3 className="text-sm font-medium">Equipped</h3>
                {view.summary.equipped.length === 0 ? (
                  <p className="mt-1 text-sm text-muted">Nothing equipped.</p>
                ) : (
                  <ul className="mt-2 text-sm" data-testid="equipped">
                    {view.summary.equipped.map((item) => (
                      <li key={`${item.slot}-${item.name}`}>
                        {item.slot}: {item.name}
                        {item.baseName ? ` (${item.baseName})` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  disabled={busy}
                  data-testid="copy-button"
                  onClick={() =>
                    run(async () => {
                      const copied = await api<{ revision: Revision; build: LibraryBuild }>(
                        `/api/library/${view.build.id}/copies`,
                        { method: "POST", body: JSON.stringify({ revisionId: view.revision.id }) },
                      );
                      await refreshHistory(view.build.id);
                      await openRevision(copied.revision.id);
                    })
                  }
                >
                  Edit a copy
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy || !isDraft}
                  data-testid="equip-button"
                  onClick={() =>
                    run(async () => {
                      const plate = await api<{ text: string; slot: string }>("/api/examples/life-plate");
                      const equipped = await api<
                        View & { comparison?: { focus?: { Life?: { delta?: number | null } } } }
                      >(`/api/builds/${view.revision.id}/equipment`, {
                        method: "POST",
                        body: JSON.stringify(plate),
                      });
                      await refreshLibrary(query);
                      await refreshHistory(view.build.id);
                      const delta = equipped.comparison?.focus?.Life?.delta;
                      showInspection(
                        { ...equipped, saved: false },
                        `Equipped on a working copy. Engine Life delta ${formatDelta(delta)}.`,
                      );
                    })
                  }
                >
                  Equip +100 life
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy || !isDraft}
                  data-testid="passive-button"
                  onClick={() =>
                    run(async () => {
                      const allocated = await api<
                        View & { passive: { name?: string; id?: number }; comparison?: { focus?: { Life?: { delta?: number | null } } } }
                      >(`/api/builds/${view.revision.id}/passives`, {
                        method: "POST",
                        body: JSON.stringify({}),
                      });
                      await refreshLibrary(query);
                      await refreshHistory(view.build.id);
                      showInspection(
                        { ...allocated, saved: false },
                        `Allocated ${allocated.passive.name} (${allocated.passive.id}) on a working copy. Engine Life delta ${formatDelta(allocated.comparison?.focus?.Life?.delta)}.`,
                      );
                    })
                  }
                >
                  Allocate life passive
                </Button>
                <Button
                  disabled={busy || !isDraft}
                  data-testid="save-button"
                  onClick={() =>
                    run(async () => {
                      const saved = await api<View>(`/api/builds/${view.revision.id}/save`, { method: "POST" });
                      await refreshLibrary(query);
                      await refreshHistory(view.build.id);
                      setLeftId(saved.revision.id);
                      showInspection(saved, "Saved a new revision. Earlier revisions were left unchanged.");
                    })
                  }
                >
                  Save
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy || !isDraft}
                  onClick={() =>
                    run(async () => {
                      const discarded = await api<{ build: LibraryBuild }>(`/api/builds/${view.revision.id}/discard`, {
                        method: "POST",
                      });
                      const nextHistory = await refreshHistory(discarded.build.id);
                      await refreshLibrary(query);
                      const revisionId = discarded.build.savedRevisionId ?? nextHistory.revisions.at(-1)?.id;
                      if (!revisionId) throw new Error("Nothing left to show.");
                      await openRevision(revisionId);
                    })
                  }
                >
                  Discard copy
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  data-testid="export-button"
                  onClick={() =>
                    run(async () => {
                      const exported = await api<{ xml: string }>(`/api/builds/${view.revision.id}/export`);
                      if (!exported.xml.includes("<PathOfBuilding")) {
                        throw new Error("Export is not Path of Building XML.");
                      }
                      setXml(exported.xml);
                      const blob = new Blob([exported.xml], { type: "application/xml" });
                      const url = URL.createObjectURL(blob);
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = `${view.build.name}.xml`;
                      link.click();
                      URL.revokeObjectURL(url);
                      setNote("Exported Path of Building XML from this revision.");
                    })
                  }
                >
                  Export XML
                </Button>
              </div>
            </section>
          ) : (
            <section className="rounded-lg border border-dashed border-border p-6 text-sm text-muted">
              Import a build to inspect it. The inspector fills in after the engine calculates.
            </section>
          )}

          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-medium">Version history</h2>
            {history.length === 0 ? (
              <p className="mt-2 text-sm text-muted">History appears after a build is opened.</p>
            ) : (
              <ul className="mt-3 flex flex-col gap-1" data-testid="history">
                {history.map((revision) => {
                  const selected = view?.revision.id === revision.id;
                  const stored = revision.id === savedId;
                  return (
                    <li key={revision.id}>
                      <button
                        type="button"
                        data-testid="history-revision"
                        data-label={revision.label}
                        className={`flex w-full items-center justify-between gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-white/5 ${selected ? "bg-white/10" : ""}`}
                        onClick={() => run(() => openRevision(revision.id))}
                        disabled={busy}
                      >
                        <span>
                          <span className="font-medium">{revisionLabel(revision.label)}</span>
                          <span className="mt-0.5 block text-xs text-muted">{formatWhen(revision.createdAt)}</span>
                        </span>
                        <span className="text-xs text-muted">
                          {stored ? "Stored" : revision.status === "draft" ? "Copy" : "Kept"}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-medium">Comparison</h2>
            <p className="mt-1 text-xs text-muted">Both sides are calculated again when you compare.</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="text-sm">
                <span className="text-muted">Left</span>
                <select
                  className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
                  value={leftId}
                  onChange={(event) => setLeftId(event.target.value)}
                  data-testid="compare-left"
                >
                  <option value="">Choose a revision</option>
                  {history.map((revision) => (
                    <option key={revision.id} value={revision.id}>
                      {revisionLabel(revision.label)} · {revision.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm">
                <span className="text-muted">Right</span>
                <select
                  className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
                  value={rightId}
                  onChange={(event) => setRightId(event.target.value)}
                  data-testid="compare-right"
                >
                  <option value="">Choose a revision</option>
                  {history.map((revision) => (
                    <option key={revision.id} value={revision.id}>
                      {revisionLabel(revision.label)} · {revision.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <Button
              className="mt-3"
              variant="secondary"
              data-testid="compare-button"
              disabled={busy || leftId === "" || rightId === ""}
              onClick={() =>
                run(async () => {
                  const result = await api<Comparison>("/api/compare", {
                    method: "POST",
                    body: JSON.stringify({ leftRevisionId: leftId, rightRevisionId: rightId }),
                  });
                  if (result.source !== "pob-engine") {
                    throw new Error("Comparison was not calculated by the engine.");
                  }
                  setComparison(result);
                  setNote(`Compared ${result.changedCount} changed stats from the engine.`);
                })
              }
            >
              Compare calculations
            </Button>
            {comparison ? (
              <div className="mt-4" data-testid="comparison">
                <p className="font-mono text-xs text-muted">
                  {comparison.source} · {comparison.changedCount} changed
                </p>
                <table className="mt-3 w-full text-left text-sm">
                  <thead className="text-muted">
                    <tr>
                      <th className="py-1 font-medium">Stat</th>
                      <th className="py-1 text-right font-medium">Left</th>
                      <th className="py-1 text-right font-medium">Right</th>
                      <th className="py-1 text-right font-medium">Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(comparison.focus).map(([stat, row]) => (
                      <tr key={stat} className="border-t border-border">
                        <td className="py-1.5">{stat}</td>
                        <td className="py-1.5 text-right font-mono">{formatStat(row.left)}</td>
                        <td className="py-1.5 text-right font-mono">{formatStat(row.right)}</td>
                        <td className="py-1.5 text-right font-mono" data-testid={`delta-${stat}`}>
                          {formatDelta(row.delta)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {comparison.changed.length > 0 ? (
                  <div className="mt-4 max-h-48 overflow-auto">
                    <table className="w-full text-left text-xs">
                      <tbody>
                        {comparison.changed.map((row) => (
                          <tr key={row.stat} className="border-t border-border">
                            <td className="py-1">{row.stat}</td>
                            <td className="py-1 text-right font-mono">{formatStat(row.left)}</td>
                            <td className="py-1 text-right font-mono">{formatStat(row.right)}</td>
                            <td className="py-1 text-right font-mono">{formatDelta(row.delta)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>

          {xml ? (
            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="text-sm font-medium">Export</h2>
              <textarea
                readOnly
                data-testid="export-xml"
                className="mt-3 h-64 w-full rounded-md border border-border bg-background p-3 font-mono text-xs"
                value={xml}
              />
            </section>
          ) : null}
        </div>
      </div>

      {error ? (
        <p className="text-sm text-danger" role="alert" data-testid="error">
          {error}
        </p>
      ) : null}
      {note ? (
        <p className="text-sm text-muted" data-testid="note">
          {note}
        </p>
      ) : null}
      {busy ? (
        <p className="text-sm text-muted" data-testid="busy">
          Calculating with Path of Building…
        </p>
      ) : null}
    </main>
  );
}
