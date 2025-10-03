export async function getBackendUrl() {
  // Use env-var for the URL-provider endpoint
  const URL_PROVIDER ="https://connect-frontend-347720367133.asia-south1.run.app"

  if (!URL_PROVIDER) throw new Error("URL provider endpoint not configured");

  const res = await fetch(URL_PROVIDER);
  if (!res.ok) throw new Error(`Failed to fetch URL: ${res.status}`);

  const data = await res.json();
  return data.url;        
}