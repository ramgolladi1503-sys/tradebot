export async function fetchHome(limit = 5) {
  const res = await fetch(`/api/home?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch home");
  return res.json();
}

export async function fetchTop(limit = 5) {
  const res = await fetch(`/api/top-opportunities?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch top opportunities");
  return res.json();
}

export async function fetchAdvisory(limit = 25) {
  const res = await fetch(`/api/advisory?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch advisory");
  return res.json();
}

export async function fetchReview(limit = 50) {
  const res = await fetch(`/api/review-queue?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch review queue");
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`/api/system-health`);
  if (!res.ok) throw new Error("Failed to fetch health");
  return res.json();
}

export function connectHomeStream(onMessage: (data: any) => void) {
  const ws = new WebSocket(`ws://${window.location.host}/ws/home`);
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch {}
  };
  return ws;
}
