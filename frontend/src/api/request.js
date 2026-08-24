export async function requestJson(authFetch, url, options, fallbackMessage) {
  const response = await authFetch(url, options);
  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    data = {};
  }

  if (!response.ok) {
    const error = new Error(data.msg || data.error || fallbackMessage || 'Request failed.');
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}
