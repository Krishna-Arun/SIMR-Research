// api.js — handles backend communication

export async function login(username) {
    const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username })
    });
    const data = await response.json();
    if (data.status !== "ok") {
        throw new Error("Login failed");
    }
    return data.user_id;  // Cookie is already set by backend
}

export async function saveResult(result) {
    const response = await fetch("/save_result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result })
    });
    const data = await response.json();
    if (data.status !== "ok") {
        throw new Error("Failed to save result");
    }
    return data;
}

export async function getResults() {
    const response = await fetch("/get_results");
    const data = await response.json();
    return data.results;
}

export async function fetchGraphData() {
    const response = await fetch("/graph-data");
    if (!response.ok) {
        throw new Error("Failed to fetch graph data");
    }
    return await response.json();
}
