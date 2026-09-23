export type Employee = {
  employee_id: string;
  full_name: string;
  department: string;
  role: string;
  grade: string;
};

export type SkillGap = {
  skill_id: string;
  name: string;
  type: string;
  category: string;
  current_level: number;
  expected_level: number;
  required_level: number;
  gap: number;
  expected_gap: number;
  critical: boolean;
  description: string;
};

export type Recommendation = {
  event_id: string;
  title: string;
  description: string;
  type: string;
  format: string;
  duration_hours: number;
  next_session: string | null;
  participation_id: string;
  score: number;
  score_label: string;
  components: Record<string, number>;
  covered_skills: { skill_id: string; name: string; gain: number; critical: boolean }[];
  explanation: string;
  factors: string[];
};

export type Career = {
  employee: Employee & { tenure_months: number; work_format: string; last_review_date: string };
  target: { role: string; grade: string; source: string };
  gaps: SkillGap[];
  current_skills: SkillGap[];
  recommendations: Recommendation[];
  snapshot_date: string;
  history: { record_id: string; event_id: string; title: string; date: string; status: string; completion_pct: number; assigned_by: string }[];
  achievements: { quests_completed: number };
  progress: {
    total_required: number;
    confirmed_ready: number;
    expected_ready: number;
    remaining_gap: number;
    expected_remaining_gap: number;
  };
};

export type HrSummary = {
  department: string;
  employee_count: number;
  top_gaps: { name: string; employees: number }[];
  employees_without_recommendations: { employee_id: string; full_name: string; target_role: string; reasons: { reason: string; events: number }[] }[];
  participation: { total_records: number; completed: number; completion_rate: number; statuses: Record<string, number> };
  events: { event_id: string; title: string; participants: number; completed: number }[];
};

export type CardAction = { kind: "explain" | "compare"; event_ids: string[] };
export type Ask = (message: string, reset?: boolean, action?: CardAction) => void;
export type View = "comparison" | "explanation" | "clarification" | "level" | "skill_map" | "route" | "next_step" | "history" | "hr_gaps" | "hr_coverage" | "hr_events" | "skill_guide";
export type Session = { token: string; employee_id: string; role: "employee" | "hr"; department: string; demo: boolean };
export type AppConfig = { demo: boolean; ai_enabled: boolean; snapshot_date: string };
export type Options = { recommendations: Recommendation[]; max_minutes: number | null; event_format: string | null; exclusions: { reason: string; events: number }[] };
export type Artifact = { kind: View; comparison?: (Partial<Recommendation> & {event_id: string; title: string; explanation: string; eligible: boolean})[]; career?: Career; hr?: HrSummary; options?: Options | null; simulation?: { event_id: string; title: string; changes: { skill_id: string; before: number; after: number }[] }[] | null; guide?: { skill: SkillGap; example: string; label: string } | null };
export type AgentReply = { conversation_id: string; message_id: string; answer: string; artifact: Artifact | null; sources: { id: string; label: string; view: View }[]; trace: { tool: string; status: string; ms: number }[]; mode: "agent" | "local" | "fallback"; notice: string; elapsed_ms: number; constraints: { max_minutes: number | null; event_format: string | null } };
