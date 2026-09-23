import { Career, Employee, HrSummary } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}

export const api = {
  employees: () => request<Employee[]>("/employees"),
  career: (employeeId: string) => request<Career>(`/employees/${employeeId}/career`),
  complete: (employeeId: string, eventId: string) =>
    request<{ career: Career }>(`/employees/${employeeId}/events/${eventId}/complete`, { method: "POST" }),
  hrSummary: () => request<HrSummary>("/hr/summary"),
};
