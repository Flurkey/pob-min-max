"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

type EngineInfo = {
  engineRevision?: string;
  versionNumber?: string;
  latestTreeVersion?: string;
  latestTreeDisplay?: string;
  revisionMatchesPin?: boolean;
  className?: string;
};

type Calculation = {
  source: string;
  level?: number;
  treeVersion?: string;
  engineRevision?: string;
  stats: Record<string, number>;
};

type Revision = { id: string; name: string; label: string };

const FOCUS = ["Life", "EnergyShield", "Mana", "Str", "Dex", "Int", "Armour", "Evasion"] as const;

async function readError(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : response.statusText;
}

function storedLife(xml: string): string | null {
  const match = xml.match(/<PlayerStat stat="Life" value="([^"]*)"/);
  return match ? match[1] : null;
}

export default function Page() {
  const [engine, setEngine] = useState<EngineInfo | null>(null);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [revision, setRevision] = useState<Revision | null>(null);
  const [baselineLife, setBaselineLife] = useState<number | null>(null);
  const [calculation, setCalculation] = useState<Calculation | null>(null);
  const [stored, setStored] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [xml, setXml] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/engine")
      .then(async (response) => {
        if (!response.ok) throw new Error(await readError(response));
        return response.json();
      })
      .then(setEngine)
      .catch((reason: Error) => setEngineError(reason.message));
  }, []);

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

  async function importXml(name: string, body: string, label: string) {
    const response = await fetch("/api/builds", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, xml: body }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const payload = await response.json();
    setRevision(payload.revision);
    setCalculation(payload.calculation);
    setStored(storedLife(body));
    setXml(null);
    setNote(label);
    if (baselineLife === null) setBaselineLife(payload.calculation.stats.Life);
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="flex flex-col gap-2">
        <p className="text-xs uppercase tracking-[0.2em] text-muted">Phase 1</p>
        <h1 className="text-3xl font-semibold">PoE Forge</h1>
        <p className="max-w-2xl text-sm text-muted">
          Stats on this page come from the Path of Building calculation engine. The Life value stored in the build XML
          is only a cache.
        </p>
      </header>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-medium">Engine</h2>
        {engineError ? (
          <p className="mt-2 text-sm text-danger" role="alert">
            {engineError}. Start the engine service, then reload.
          </p>
        ) : engine ? (
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted">Revision</dt>
              <dd className="font-mono text-xs">{engine.engineRevision}</dd>
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

      <section className="flex flex-wrap gap-2">
        <Button
          disabled={busy || !engine}
          onClick={() =>
            run(async () => {
              const fixture = await fetch("/api/fixtures/scion-baseline");
              if (!fixture.ok) throw new Error(await readError(fixture));
              const file = await fixture.json();
              setBaselineLife(null);
              await importXml(file.name, file.xml, "Imported the engine-exported Scion baseline.");
            })
          }
        >
          Import baseline
        </Button>
        <Button
          variant="secondary"
          disabled={busy || !revision}
          onClick={() =>
            run(async () => {
              const fixture = await fetch("/api/fixtures/scion-baseline");
              if (!fixture.ok) throw new Error(await readError(fixture));
              const file = await fixture.json();
              const forged = file.xml.replace('stat="Life" value="60"', 'stat="Life" value="999999"');
              await importXml("Forged cache", forged, "Imported the same build with the stored Life tag set to 999999.");
            })
          }
        >
          Forge stored Life
        </Button>
        <Button
          variant="secondary"
          disabled={busy || !revision}
          onClick={() =>
            run(async () => {
              const example = await fetch("/api/examples/life-plate");
              if (!example.ok) throw new Error(await readError(example));
              const plate = await example.json();
              const response = await fetch(`/api/builds/${revision!.id}/equipment`, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify(plate),
              });
              if (!response.ok) throw new Error(await readError(response));
              const payload = await response.json();
              setRevision(payload.revision);
              setCalculation(payload.calculation);
              setStored(null);
              setXml(null);
              const delta = payload.comparison?.focus?.Life?.delta;
              setNote(`Equipped ${payload.equipment.baseName}. Life delta ${delta}.`);
            })
          }
        >
          Equip +100 life
        </Button>
        <Button
          variant="secondary"
          disabled={busy || !revision}
          onClick={() =>
            run(async () => {
              const response = await fetch(`/api/builds/${revision!.id}/passives`, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({}),
              });
              if (!response.ok) throw new Error(await readError(response));
              const payload = await response.json();
              setRevision(payload.revision);
              setCalculation(payload.calculation);
              setStored(null);
              setXml(null);
              setNote(
                `Allocated ${payload.passive.name} (${payload.passive.id}). Life delta ${payload.comparison?.focus?.Life?.delta}.`,
              );
            })
          }
        >
          Allocate life passive
        </Button>
        <Button
          variant="ghost"
          disabled={busy || !revision}
          onClick={() =>
            run(async () => {
              const response = await fetch(`/api/builds/${revision!.id}/export`);
              if (!response.ok) throw new Error(await readError(response));
              const payload = await response.json();
              setXml(payload.xml);
              setNote("Exported XML from the current engine build.");
            })
          }
        >
          Export XML
        </Button>
      </section>

      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
      {note ? <p className="text-sm text-muted">{note}</p> : null}

      {calculation ? (
        <section className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="text-sm font-medium">
              {calculation.source} · level {calculation.level} · tree {calculation.treeVersion}
            </h2>
            <p className="font-mono text-xs text-muted">{revision?.label}</p>
          </div>
          {stored ? (
            <p className="mt-2 text-sm">
              Stored Life cache: <span className="font-mono">{stored}</span>. Engine Life:{" "}
              <span className="font-mono">{calculation.stats.Life}</span>.
            </p>
          ) : null}
          {baselineLife !== null ? (
            <p className="mt-1 text-sm text-muted">
              Change from the first import this session: {calculation.stats.Life - baselineLife}
            </p>
          ) : null}
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-1 font-medium">Stat</th>
                <th className="py-1 font-medium">Engine</th>
              </tr>
            </thead>
            <tbody>
              {FOCUS.map((stat) => (
                <tr key={stat} className="border-t border-border">
                  <td className="py-1.5">{stat}</td>
                  <td className="py-1.5 font-mono">{calculation.stats[stat] ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {xml ? (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="text-sm font-medium">Export</h2>
          <textarea
            readOnly
            className="mt-3 h-64 w-full rounded-md border border-border bg-background p-3 font-mono text-xs"
            value={xml}
          />
        </section>
      ) : null}
    </main>
  );
}
