import { Career, Employee, HrSummary, Session, AppConfig, AgentReply, CardAction } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Не удалось выполнить запрос (${response.status})`);
  }
  return response.json();
}

export const api = {
  config: () => request<AppConfig>("/config"),
  demoProfiles: () => request<Employee[]>("/demo/profiles"),
  login: (employee_id: string, role: Session["role"], access_code = "") => request<Session>("/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ employee_id, role, access_code }) }),
  employees: () => request<Employee[]>("/employees"),
  career: (employeeId: string) => request<Career>(`/employees/${employeeId}/career`),
  complete: (employeeId: string, eventId: string) =>
    request<{ career: Career }>(`/employees/${employeeId}/events/${eventId}/complete`, { method: "POST" }),
  hrSummary: () => request<HrSummary>("/hr/summary"),
};

export function scopedApi(token: string) {
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  return {
    career: (id: string, signal?: AbortSignal) => request<Career>(`/employees/${encodeURIComponent(id)}/career`, { headers, signal }),
    hr: (signal?: AbortSignal) => request<HrSummary>("/hr/summary", { headers, signal }),
    restore: () => request<Omit<Session,"token">>("/session", { headers }),
    goals: () => request<{role:string;grade:string}[]>("/goals", { headers }),
    goal: (id:string, role:string, grade:string) => request<Career>(`/employees/${encodeURIComponent(id)}/goal`, { method:"PUT", headers, body:JSON.stringify({role,grade}) }),
    complete: (id: string, eventId: string, participationId: string) => request<{ career: Career; already_completed: boolean }>(`/employees/${encodeURIComponent(id)}/events/${encodeURIComponent(eventId)}/complete`, { method: "POST", headers, body: JSON.stringify({participation_id: participationId}) }),
    assistant: (message: string, reset = false, signal?: AbortSignal, conversationId?: string, action?: CardAction) => request<AgentReply>("/assistant", { method: "POST", headers, signal, body: JSON.stringify({ message, reset_constraints: reset, conversation_id: conversationId, action }) }),
    logout: () => request<{ logged_out: boolean }>("/session", { method: "DELETE", headers }),
  };
}
