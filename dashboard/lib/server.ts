import "server-only";

const API_URL = process.env.NEXUS_API_URL ?? "http://127.0.0.1:8000";

/** URL de invitación general del bot (sin servidor), leída de la API en el servidor de Next. */
export async function getInviteUrl(): Promise<string | null> {
  try {
    const res = await fetch(`${API_URL}/api/v1/invite`, { next: { revalidate: 300 } });
    if (!res.ok) return null;
    const data = (await res.json()) as { invite_url: string | null };
    return data.invite_url;
  } catch {
    return null;
  }
}
