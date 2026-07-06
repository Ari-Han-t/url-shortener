// State
let isLoginMode = true;
const API_BASE = ""; // Relative to the same domain

// DOM Elements
const authSection = document.getElementById("authSection");
const dashboardSection = document.getElementById("dashboardSection");
const authForm = document.getElementById("authForm");
const shortenForm = document.getElementById("shortenForm");
const logoutBtn = document.getElementById("logoutBtn");
const qrModal = document.getElementById("qrModal");

// Auth Tabs
function switchAuthTab(mode) {
    isLoginMode = mode === 'login';
    const tabs = document.querySelectorAll(".tab");
    tabs[0].classList.toggle("active", isLoginMode);
    tabs[1].classList.toggle("active", !isLoginMode);
    document.getElementById("authSubmitBtn").textContent = isLoginMode ? "Login" : "Register";
    document.getElementById("authError").textContent = "";
}

// Init
function init() {
    const token = localStorage.getItem("token");
    if (token) {
        showDashboard();
    } else {
        showAuth();
    }
}

function showAuth() {
    authSection.classList.remove("hidden");
    dashboardSection.classList.add("hidden");
    logoutBtn.classList.add("hidden");
}

function showDashboard() {
    authSection.classList.add("hidden");
    dashboardSection.classList.remove("hidden");
    logoutBtn.classList.remove("hidden");
    fetchAnalytics();
}

// Auth Submit
authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const errorEl = document.getElementById("authError");
    
    errorEl.textContent = "Loading...";

    try {
        if (isLoginMode) {
            // Login
            const formData = new URLSearchParams();
            formData.append("username", username);
            formData.append("password", password);
            
            const res = await fetch(`${API_BASE}/token`, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: formData
            });
            const data = await res.json();
            
            if (res.ok) {
                localStorage.setItem("token", data.access_token);
                errorEl.textContent = "";
                showDashboard();
            } else {
                errorEl.textContent = data.detail || "Login failed";
            }
        } else {
            // Register
            const res = await fetch(`${API_BASE}/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            
            if (res.ok) {
                errorEl.textContent = "Registration successful! Please login.";
                errorEl.style.color = "var(--primary)";
                switchAuthTab('login');
            } else {
                errorEl.textContent = data.detail || "Registration failed";
                errorEl.style.color = "var(--error)";
            }
        }
    } catch (err) {
        errorEl.textContent = "Network error occurred.";
    }
});

// Logout
logoutBtn.addEventListener("click", () => {
    localStorage.removeItem("token");
    showAuth();
});

// Fetch Analytics
async function fetchAnalytics() {
    const token = localStorage.getItem("token");
    try {
        // Since we don't have a "fetch all links" endpoint directly, we fetch analytics for a dummy short_id to get dashboard data
        // Wait, our /analytics/{short_id} endpoint returns the dashboard data for the whole user!
        // We can just hit /analytics/dummy (it doesn't matter what short_id we pass because the backend queries by user_id)
        
        const res = await fetch(`${API_BASE}/analytics/dummy`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        
        if (res.status === 401) {
            localStorage.removeItem("token");
            showAuth();
            return;
        }

        const data = await res.json();
        
        document.getElementById("totalClicks").textContent = data["Total Network Clicks"];
        
        const links = data["Dashboard"] || [];
        document.getElementById("totalLinks").textContent = links.length;
        
        const tbody = document.getElementById("linksTableBody");
        tbody.innerHTML = "";
        
        links.forEach(link => {
            const shortUrl = `${window.location.origin}/${link["Short ID"]}`;
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><a href="${shortUrl}" target="_blank">${link["Short ID"]}</a></td>
                <td><span style="max-width: 200px; display: inline-block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${link["Long URL"]}</span></td>
                <td>${link["Total Clicks"]}</td>
                <td>
                    <button class="qr-btn" onclick="openQrModal('${link["Short ID"]}')">QR</button>
                </td>
            `;
            tbody.appendChild(tr);
        });

    } catch (err) {
        console.error("Failed to fetch dashboard data", err);
    }
}

// Shorten Link
shortenForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const longUrl = document.getElementById("longUrl").value;
    const customAlias = document.getElementById("customAlias").value;
    const errorEl = document.getElementById("shortenError");
    const resultBox = document.getElementById("shortenResult");
    const token = localStorage.getItem("token");
    
    errorEl.textContent = "Shortening...";
    resultBox.classList.add("hidden");

    try {
        const payload = { long_url: longUrl };
        if (customAlias) {
            payload.custom_id = customAlias;
        }

        const res = await fetch(`${API_BASE}/shorten`, {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (res.ok) {
            errorEl.textContent = "";
            const shortUrl = `${window.location.origin}/${data.Short_ID}`;
            document.getElementById("resultLink").textContent = shortUrl;
            document.getElementById("resultLink").href = shortUrl;
            resultBox.classList.remove("hidden");
            
            // Clear inputs
            document.getElementById("longUrl").value = "";
            document.getElementById("customAlias").value = "";
            
            // Refresh table
            fetchAnalytics();
        } else {
            errorEl.textContent = data.detail || data.Message || "Failed to shorten link";
        }
    } catch (err) {
        errorEl.textContent = "Network error occurred.";
    }
});

// QR Modal
function openQrModal(shortId) {
    const qrImage = document.getElementById("qrImage");
    // Show a loading state or just directly load
    qrImage.src = `${API_BASE}/qrcode/${shortId}`;
    qrModal.classList.remove("hidden");
}

function closeQrModal() {
    qrModal.classList.add("hidden");
}

// Run init
init();
