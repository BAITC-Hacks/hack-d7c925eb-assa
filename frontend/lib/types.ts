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
};

export type Recommendation = {
  event_id: string;
  title: string;
  description: string;
  type: string;
  format: string;
  duration_hours: number;
  next_session: string | null;
  score: number;
  score_label: string;
  components: Record<string, number>;
  covered_skills: { skill_id: string; name: string; gain: number; critical: boolean }[];
  explanation: string;
};

export type Career = {
  employee: Employee & { tenure_months: number; work_format: string; last_review_date: string };
  target: { role: string; grade: string; source: string };
  gaps: SkillGap[];
  recommendations: Recommendation[];
  progress: {
    total_required: number;
    confirmed_ready: number;
    expected_ready: number;
    remaining_gap: number;
    expected_remaining_gap: number;
  };
};

export type HrSummary = {
  top_gaps: { name: string; employees: number }[];
  employees_without_recommendations: { employee_id: string; full_name: string; target_role: string }[];
  participation: { total_records: number; completed: number; completion_rate: number; statuses: Record<string, number> };
};
