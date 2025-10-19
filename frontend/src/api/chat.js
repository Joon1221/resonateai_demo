const BASE = import.meta.env.VITE_API_BASE ?? ""; // e.g. "http://localhost:8000"

export async function postChat(flow, messages) {
  const res = await fetch(`${BASE}/api/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flow, messages }),
  });
  if (!res.ok) throw new Error(`Chat error ${res.status}`);
  return await res.json(); // { reply: string } in your current backend
}
