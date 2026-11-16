export type EngineInfo = {
  engineRevision?: string;
  versionNumber?: string;
  latestTreeVersion?: string;
  latestTreeDisplay?: string;
  revisionMatchesPin?: boolean;
};

export type Calculation = {
  source: string;
  level?: number;
  treeVersion?: string;
  engineRevision?: string;
  manifestVersion?: string;
  stats: Record<string, number>;
};

export type BuildSummary = {
  source: string;
  className?: string | null;
  ascendClassName?: string | null;
  level?: number | null;
  treeVersion?: string | null;
  treeDisplay?: string | null;
  allocatedPoints?: number | null;
  equipped: { slot?: string | null; name?: string | null; baseName?: string | null }[];
};

export type Revision = {
  id: string;
  buildId: string;
  parentId?: string | null;
  name: string;
  label: string;
  status: "saved" | "draft" | string;
  createdAt: string;
  engineRevision?: string | null;
  treeVersion?: string | null;
};

export type LibraryBuild = {
  id: string;
  name: string;
  savedRevisionId?: string | null;
  createdAt: string;
  updatedAt: string;
  savedLabel?: string | null;
  treeVersion?: string | null;
  engineRevision?: string | null;
};

export type Inspection = {
  revision: Revision;
  build: LibraryBuild;
  saved: boolean;
  calculation: Calculation;
  summary: BuildSummary;
};

export type Comparison = {
  source: string;
  leftRevisionId: string;
  rightRevisionId: string;
  focus: Record<string, { left?: number | null; right?: number | null; delta?: number | null }>;
  changedCount: number;
  changed: { stat: string; left?: number | null; right?: number | null; delta?: number | null }[];
};
