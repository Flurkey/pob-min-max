import { formatStat } from "@/lib/format";

const GROUPS = [
  {
    title: "Defence",
    keys: [
      "Life",
      "LifeUnreserved",
      "EnergyShield",
      "Mana",
      "Armour",
      "Evasion",
      "Ward",
      "FireResist",
      "ColdResist",
      "LightningResist",
      "ChaosResist",
    ],
  },
  {
    title: "Offence",
    keys: ["TotalDPS", "FullDPS", "CombinedDPS", "AverageDamage", "Speed", "CritChance", "HitChance", "ManaCost"],
  },
  {
    title: "Attributes",
    keys: ["Str", "Dex", "Int"],
  },
] as const;

export function StatTable({ stats }: { stats: Record<string, number> }) {
  return (
    <div className="flex flex-col gap-4">
      {GROUPS.map((group) => (
        <table key={group.title} className="w-full text-left text-sm">
          <thead className="text-muted">
            <tr>
              <th className="py-1 font-medium">{group.title}</th>
              <th className="py-1 text-right font-medium">Engine</th>
            </tr>
          </thead>
          <tbody>
            {group.keys.map((key) => (
              <tr key={key} className="border-t border-border">
                <td className="py-1.5">{key}</td>
                <td className="py-1.5 text-right font-mono" data-testid={`stat-${key}`}>
                  {formatStat(stats[key])}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </div>
  );
}
