const API_BASE = "http://127.0.0.1:5000/api";
const API_ROOT = API_BASE.replace(/\/api$/, "");
const STORAGE_KEYS = {
    sidebarCollapsed: "devforum.sidebarCollapsed"
};

let allPosts = [];
let currentUser = null;
let currentUserId = null;
let currentUserAvatar = null;
let currentProfile = null;
let problemSets = [];
let communities = [];
let notifications = [];
let selectedProblemId = null;
let currentSection = "feed";

async function apiRequest(path, options = {}) {
    const token = localStorage.getItem("token");
    const {
        method = "GET",
        body = null,
        auth = true,
        headers = {}
    } = options;

    const requestHeaders = { ...headers };
    if (auth && token) {
        requestHeaders.Authorization = `Bearer ${token}`;
    }

    let requestBody = body;
    if (body && !(body instanceof FormData)) {
        requestHeaders["Content-Type"] = "application/json";
        requestBody = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE}${path}`, {
        method,
        headers: requestHeaders,
        body: requestBody
    });

    let data = null;
    try {
        data = await response.json();
    } catch (error) {
        data = null;
    }

    if (!response.ok && data?.msg?.includes("expired")) {
        logout();
    }

    return { response, data };
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function escapeForTemplateLiteral(value) {
    return String(value ?? "")
        .replace(/\\/g, "\\\\")
        .replace(/`/g, "\\`")
        .replace(/\$/g, "\\$")
        .replace(/\r?\n/g, "\\n");
}

function getInitials(name) {
    return String(name || "?")
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map(part => part.charAt(0).toUpperCase())
        .join("") || "?";
}

function resolveAssetUrl(url) {
    if (!url) return null;
    return url.startsWith("http") ? url : `${API_ROOT}${url}`;
}

function buildAvatar(url, name, className = "avatar") {
    const resolvedUrl = resolveAssetUrl(url);

    if (resolvedUrl) {
        return `<img class="${className}" src="${resolvedUrl}" alt="${escapeHtml(name)} avatar">`;
    }

    const placeholderClass = className === "profile-avatar"
        ? "profile-avatar-placeholder"
        : "avatar-placeholder";

    return `<div class="${placeholderClass}">${escapeHtml(getInitials(name))}</div>`;
}

function formatRelativeAge(value) {
    if (typeof value === "string" && Number.isNaN(Number(value))) {
        return value;
    }

    const age = Number(value || 0);
    if (age <= 0) return "Fresh";
    if (age === 1) return "1 hour ago";
    if (age < 24) return `${age} hours ago`;

    const days = Math.floor(age / 24);
    return days === 1 ? "1 day ago" : `${days} days ago`;
}

function setActiveSection(section) {
    currentSection = section;
    document.querySelectorAll(".nav-btn[data-section]").forEach(button => {
        button.classList.toggle("active", button.dataset.section === section);
    });
}

function switchSection(section) {
    const sections = {
        feed: "feedContent",
        trending: "trendingContent",
        "problem-sets": "problemSetsContent",
        communities: "communitiesContent",
        profile: "profileSection"
    };

    Object.entries(sections).forEach(([key, id]) => {
        const element = document.getElementById(id);
        if (element) {
            element.style.display = key === section ? "block" : "none";
        }
    });

    setActiveSection(section);
    closeSidebar();
}

function closeSidebar() {
    const sidebar = document.getElementById("sidebar");
    if (window.innerWidth <= 860) {
        sidebar?.classList.remove("open");
    }
}

async function showFeed() {
    switchSection("feed");
    await loadPosts();
}

async function showTrending() {
    switchSection("trending");
    await Promise.all([loadTrending(), loadLeaderboard()]);
}

async function showProblemSets() {
    switchSection("problem-sets");
    await loadProblemSets();
}

async function showCommunities() {
    switchSection("communities");
    await loadCommunities();
}

async function showProfile() {
    switchSection("profile");
    await loadProfile();
}

async function login() {
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    const { response, data } = await apiRequest("/auth/login", {
        method: "POST",
        auth: false,
        body: { username, password }
    });

    if (response.ok) {
        localStorage.setItem("token", data.access_token);
        window.location.href = "dashboard.html";
    } else {
        document.getElementById("message").innerText = data?.msg || data?.error || "Login failed";
    }
}

async function register() {
    const username = document.getElementById("regUsername").value;
    const email = document.getElementById("regEmail").value;
    const password = document.getElementById("regPassword").value;

    const { response, data } = await apiRequest("/auth/register", {
        method: "POST",
        auth: false,
        body: { username, email, password }
    });

    if (response.ok) {
        document.getElementById("regMessage").innerText = "Registration successful. Please login.";
        showLogin();
    } else {
        document.getElementById("regMessage").innerText = data?.msg || data?.error || "Registration failed";
    }
}

function showRegister() {
    document.querySelector(".login-card").innerHTML = `
        <h2>Join DevForum AI</h2>
        <p class="login-subtitle">Start your developer journey</p>
        <input type="text" id="regUsername" placeholder="Username" required>
        <input type="email" id="regEmail" placeholder="Email" required>
        <input type="password" id="regPassword" placeholder="Password" required>
        <button onclick="register()">Create Account</button>
        <div id="regMessage" class="error-message"></div>
        <p class="signup-link">Already have an account? <a href="#" onclick="showLogin()">Sign in</a></p>
    `;
}

function showLogin() {
    document.querySelector(".login-card").innerHTML = `
        <h2>Welcome to DevForum AI</h2>
        <p class="login-subtitle">Connect with developers worldwide</p>
        <input type="text" id="username" placeholder="Username" required>
        <input type="password" id="password" placeholder="Password" required>
        <button onclick="login()">Sign In</button>
        <div id="message" class="error-message"></div>
        <p class="signup-link">New here? <a href="#" onclick="showRegister()">Create an account</a></p>
    `;
}

function buildPostCard(post) {
    const isOwner =
        currentUserId !== null
            ? Number(post.user_id) === Number(currentUserId)
            : post.username === currentUser;

    const safeTitleArg = escapeForTemplateLiteral(post.title);
    const safeContentArg = escapeForTemplateLiteral(post.content);
    const previewText = String(post.content || "");

    return `
        <article class="post-card" onclick="loadPostDetails(${post.id}, \`${safeTitleArg}\`, \`${safeContentArg}\`)">
            <div class="post-header">
                ${buildAvatar(post.avatar_url, post.username)}
                <div>
                    <div class="post-title">${escapeHtml(post.title)}</div>
                    <div class="meta">Posted by ${escapeHtml(post.username)}</div>
                </div>
            </div>
            <p class="post-excerpt">${escapeHtml(previewText.slice(0, 140))}${previewText.length > 140 ? "..." : ""}</p>
            <div class="post-footer">
                <span class="tag">#${escapeHtml(post.post_type || "discussion")}</span>
                ${post.community_name ? `<span class="tag">${escapeHtml(post.community_name)}</span>` : `<span class="tag">Main Feed</span>`}
            </div>
            ${isOwner ? `<button class="delete-btn" onclick="event.stopPropagation(); deletePost(${post.id})">Delete</button>` : ""}
        </article>
    `;
}

async function loadTrending() {
    const { data } = await apiRequest("/posts/trending", { auth: false });
    const container = document.getElementById("trending");
    if (!container) return;

    container.innerHTML = "";

    if (!Array.isArray(data) || data.length === 0) {
        container.innerHTML = `<p class="empty-state">No trending posts yet. Start a post to get the board moving.</p>`;
        return;
    }

    data.forEach(post => {
        container.innerHTML += `
            <article class="trend-card">
                <div class="trend-header">
                    <div class="trend-author">
                        ${buildAvatar(post.avatar_url, post.username)}
                        <div>
                            <strong>${escapeHtml(post.username)}</strong>
                            <span class="trend-meta">${formatRelativeAge(post.age_hours)}</span>
                        </div>
                    </div>
                </div>
                <div class="trend-title">${escapeHtml(post.title)}</div>
                <p class="trend-summary">Trending score ${post.trending_score} built from votes and recency.</p>
                <div class="trend-metrics">
                    <span class="metric-pill">Score ${post.total_score}</span>
                    <span class="metric-pill">Age ${post.age_hours}h</span>
                    <span class="status-pill">Momentum ${post.trending_score}</span>
                </div>
            </article>
        `;
    });
}

async function loadPosts() {
    const container = document.getElementById("posts");
    if (!container) return;

    container.innerHTML = `<p class="empty-state">Loading posts...</p>`;
    const { response, data } = await apiRequest("/posts/");

    if (!response.ok) {
        container.innerHTML = `<p class="empty-state">${escapeHtml(data?.msg || data?.error || "Unable to load posts")}</p>`;
        return;
    }

    allPosts = Array.isArray(data) ? data : [];
    renderPosts(allPosts);
}

function renderPosts(posts) {
    const container = document.getElementById("posts");
    if (!container) return;

    if (!Array.isArray(posts) || posts.length === 0) {
        container.innerHTML = `<p class="empty-state">No matching posts found.</p>`;
        return;
    }

    container.innerHTML = posts.map(buildPostCard).join("");
}

async function loadPostDetails(postId, title, content) {
    document.getElementById("postsListSection").style.display = "none";
    document.getElementById("postDetailsSection").style.display = "block";
    window.scrollTo(0, 0);

    const container = document.getElementById("postDetails");
    container.innerHTML = `
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(content)}</p>
        <hr>
        <h4>Comments</h4>
        <div id="commentsSection"></div>
        <textarea id="newComment" placeholder="Write a comment..." rows="3"></textarea>
        <button onclick="addComment(${postId})">Add Comment</button>
        <hr>
    `;

    const { data } = await apiRequest(`/comments/${postId}`, { auth: false });
    const commentsDiv = document.getElementById("commentsSection");
    const comments = Array.isArray(data) ? data : [];

    comments.sort((a, b) => b.is_accepted - a.is_accepted);

    commentsDiv.innerHTML = comments.map(comment => {
        const acceptedClass = comment.is_accepted ? "accepted" : "";
        return `
            <div class="comment ${acceptedClass}">
                <p>${escapeHtml(comment.content)}</p>
                <small>By ${escapeHtml(comment.username)}</small><br>
                <small>Score: ${comment.score}</small><br>
                <button onclick="vote(${comment.id}, 'upvote', ${postId})">Upvote</button>
                <button onclick="vote(${comment.id}, 'downvote', ${postId})">Downvote</button>
                ${
                    comment.is_accepted
                        ? "<strong style='color:#4CAF50;'>Accepted Answer</strong>"
                        : `<button onclick="acceptAnswer(${comment.id}, ${postId})">Accept Answer</button>`
                }
                ${comment.username === currentUser ? `<button class="delete-btn" onclick="deleteComment(${comment.id}, ${postId})">Delete</button>` : ""}
            </div>
        `;
    }).join("");
}

async function addComment(postId) {
    const content = document.getElementById("newComment").value.trim();
    if (!content) {
        alert("Comment cannot be empty");
        return;
    }

    const { response, data } = await apiRequest(`/comments/${postId}`, {
        method: "POST",
        body: { content }
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Error adding comment");
        return;
    }

    document.getElementById("newComment").value = "";
    await Promise.all([
        loadPostDetails(
            postId,
            document.querySelector("#postDetails h3").innerText,
            document.querySelector("#postDetails p").innerText
        ),
        loadNotifications(),
        currentSection === "profile" ? loadProfile() : Promise.resolve()
    ]);
}

async function vote(commentId, type, postId) {
    const { response, data } = await apiRequest(`/comments/vote/${commentId}`, {
        method: "POST",
        body: { vote_type: type }
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to vote");
        return;
    }

    await Promise.all([
        loadPostDetails(
            postId,
            document.querySelector("#postDetails h3").innerText,
            document.querySelector("#postDetails p").innerText
        ),
        loadLeaderboard(),
        currentSection === "profile" ? loadProfile() : Promise.resolve()
    ]);
}

async function acceptAnswer(commentId, postId) {
    const { response, data } = await apiRequest(`/comments/accept/${commentId}`, {
        method: "POST"
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to accept answer");
        return;
    }

    await Promise.all([
        loadPostDetails(
            postId,
            document.querySelector("#postDetails h3").innerText,
            document.querySelector("#postDetails p").innerText
        ),
        loadLeaderboard(),
        loadNotifications(),
        currentSection === "profile" ? loadProfile() : Promise.resolve()
    ]);
}

async function createPost() {
    const title = document.getElementById("postTitle").value.trim();
    const content = document.getElementById("postContent").value.trim();
    const communityValue = document.getElementById("postCommunity")?.value || "";

    if (!title || !content) {
        alert("Title and content required");
        return;
    }

    const body = {
        title,
        content,
        community_id: communityValue ? Number(communityValue) : null,
        post_type: communityValue ? "community" : "discussion"
    };

    const { response, data } = await apiRequest("/posts/", {
        method: "POST",
        body
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Error creating post");
        return;
    }

    document.getElementById("postTitle").value = "";
    document.getElementById("postContent").value = "";
    document.getElementById("postCommunity").value = "";

    await Promise.all([
        loadPosts(),
        loadTrending(),
        loadCommunities(),
        currentSection === "profile" ? loadProfile() : Promise.resolve()
    ]);
}

function searchPosts() {
    const query = document.getElementById("searchInput").value.trim().toLowerCase();

    if (!query) {
        renderPosts(allPosts);
        return;
    }

    renderPosts(
        allPosts.filter(post => {
            const title = String(post.title || "").toLowerCase();
            const content = String(post.content || "").toLowerCase();
            const username = String(post.username || "").toLowerCase();
            const community = String(post.community_name || "").toLowerCase();
            return title.includes(query) || content.includes(query) || username.includes(query) || community.includes(query);
        })
    );
}

function buildDynamicBadges(profile) {
    const badges = [];
    if ((profile?.solved_problems || 0) >= 1) badges.push("Problem Solver");
    if ((profile?.solved_problems || 0) >= 3) badges.push("Challenge Finisher");
    if ((profile?.joined_communities || 0) >= 2) badges.push("Community Builder");
    if ((profile?.experience_points || 0) >= 120) badges.push("Mentor Momentum");
    return badges;
}

async function loadProfile() {
    const profileSection = document.getElementById("profileSection");
    if (!profileSection) return;

    const [{ response, data }, badgesResult] = await Promise.all([
        apiRequest("/profile/"),
        apiRequest("/profile/badges")
    ]);

    if (!response.ok) {
        alert(data?.msg || data?.error || "Error loading profile");
        return;
    }

    currentProfile = data;
    currentUser = data.username;
    currentUserId = data.user_id;
    currentUserAvatar = data.avatar_url;

    const apiBadges = Array.isArray(badgesResult.data) ? badgesResult.data.map(badge => badge.badge_name) : [];
    const mergedBadges = [...new Set([...apiBadges, ...buildDynamicBadges(data)])];
    const badgeHTML = mergedBadges.length > 0
        ? mergedBadges.map(badge => `<span class="badge-pill">${escapeHtml(badge)}</span>`).join("")
        : `<p class="empty-state">No badges yet. Keep posting and helping others.</p>`;

    profileSection.innerHTML = `
        <div class="profile-shell">
            <div class="profile-hero">
                <section class="profile-panel">
                    <div class="profile-identity">
                        ${buildAvatar(data.avatar_url, data.username, "profile-avatar")}
                        <div class="profile-copy">
                            <p class="eyebrow">Your public profile</p>
                            <h2>${escapeHtml(data.username)}</h2>
                            <p>Reputation ${data.reputation} plus ${data.experience_points} experience points from problem solving and communities.</p>
                            <div class="profile-actions">
                                <label class="file-upload-label">
                                    <input type="file" id="avatarInput" accept="image/png,image/jpeg,image/jpg,image/gif,image/webp" onchange="uploadProfileAvatar()">
                                    Choose profile photo
                                </label>
                            </div>
                            <small class="upload-hint">Upload a square image from your device. Max size 5 MB.</small>
                        </div>
                    </div>
                </section>

                <section class="profile-stats">
                    <p class="eyebrow">Snapshot</p>
                    <h3>Profile Stats</h3>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <span>Reputation</span>
                            <strong>${data.reputation}</strong>
                        </div>
                        <div class="stat-card">
                            <span>Total Posts</span>
                            <strong>${data.total_posts}</strong>
                        </div>
                        <div class="stat-card">
                            <span>Total Comments</span>
                            <strong>${data.total_comments}</strong>
                        </div>
                        <div class="stat-card">
                            <span>Accepted Answers</span>
                            <strong>${data.accepted_answers}</strong>
                        </div>
                        <div class="stat-card">
                            <span>Solved Problems</span>
                            <strong>${data.solved_problems}</strong>
                        </div>
                        <div class="stat-card">
                            <span>Level</span>
                            <strong>${escapeHtml(data.level_name || "Beginner")}</strong>
                        </div>
                    </div>
                </section>
            </div>

            <section class="profile-badges">
                <p class="eyebrow">Recognition</p>
                <h3>Badges</h3>
                <div class="badges-grid">${badgeHTML}</div>
            </section>
        </div>
    `;
}

async function uploadProfileAvatar() {
    const input = document.getElementById("avatarInput");
    const file = input?.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("avatar", file);

    const { response, data } = await apiRequest("/profile/avatar", {
        method: "POST",
        body: formData
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to upload avatar");
        return;
    }

    currentUserAvatar = data.avatar_url;
    await Promise.all([loadProfile(), loadPosts(), loadTrending(), loadLeaderboard()]);
}

async function loadLeaderboard() {
    const { data } = await apiRequest("/profile/leaderboard", { auth: false });
    const container = document.getElementById("leaderboard");
    if (!container) return;

    if (!Array.isArray(data) || data.length === 0) {
        container.innerHTML = `<p class="empty-state">No leaderboard data yet.</p>`;
        return;
    }

    const medals = ["#1", "#2", "#3"];
    container.innerHTML = data.map((user, index) => {
        const rankClass = `rank-${index + 1}`;
        const rankLabel = medals[index] || `#${index + 1}`;
        const levelMeta = user.level_name ? ` · ${user.level_name}` : "";
        return `
            <div class="leaderboard-item ${rankClass}">
                <div class="leaderboard-identity">
                    ${buildAvatar(user.avatar_url, user.username)}
                    <div class="leaderboard-copy">
                        <strong>${escapeHtml(user.username)}</strong>
                        <span class="meta">${rankLabel} on the board${escapeHtml(levelMeta)}</span>
                    </div>
                </div>
                <span class="lb-score">${user.reputation} pts</span>
            </div>
        `;
    }).join("");
}

function logout() {
    localStorage.removeItem("token");
    window.location.href = "index.html";
}

async function deletePost(postId) {
    if (!confirm("Are you sure you want to delete this post?")) return;

    const { response, data } = await apiRequest(`/posts/${postId}`, {
        method: "DELETE"
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Error deleting post");
        return;
    }

    await Promise.all([
        loadPosts(),
        loadTrending(),
        loadCommunities(),
        currentSection === "profile" ? loadProfile() : Promise.resolve()
    ]);
}

async function deleteComment(commentId, postId) {
    if (!confirm("Are you sure you want to delete this comment?")) return;

    const { response, data } = await apiRequest(`/comments/${commentId}`, {
        method: "DELETE"
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Error deleting comment");
        return;
    }

    await Promise.all([
        loadPostDetails(
            postId,
            document.querySelector("#postDetails h3").innerText,
            document.querySelector("#postDetails p").innerText
        ),
        currentSection === "profile" ? loadProfile() : Promise.resolve()
    ]);
}

function backToPostsList() {
    document.getElementById("postDetailsSection").style.display = "none";
    document.getElementById("postsListSection").style.display = "grid";
    window.scrollTo(0, 0);
}

function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    if (window.innerWidth <= 860) {
        sidebar?.classList.toggle("open");
    }
}

function scrollSidebarToBottom() {
    const sidebar = document.getElementById("sidebar");
    if (!sidebar) return;

    sidebar.scrollTo({
        top: sidebar.scrollHeight,
        behavior: "smooth"
    });
}

function toggleSidebarCollapse() {
    if (window.innerWidth <= 860) {
        toggleSidebar();
        return;
    }

    const shell = document.querySelector(".app-shell");
    const collapsed = shell?.classList.toggle("sidebar-collapsed");
    localStorage.setItem(STORAGE_KEYS.sidebarCollapsed, collapsed ? "1" : "0");
    syncSidebarCollapseState();
}

function syncSidebarCollapseState() {
    const shell = document.querySelector(".app-shell");
    const collapsed = shell?.classList.contains("sidebar-collapsed");
    const icon = document.getElementById("sidebarCollapseIcon");
    if (icon) {
        icon.textContent = collapsed ? ">" : "<";
    }
}

function applySavedSidebarState() {
    const shell = document.querySelector(".app-shell");
    if (!shell) return;

    if (window.innerWidth > 860 && localStorage.getItem(STORAGE_KEYS.sidebarCollapsed) === "1") {
        shell.classList.add("sidebar-collapsed");
    } else {
        shell.classList.remove("sidebar-collapsed");
    }

    syncSidebarCollapseState();
}

function toggleTheme() {
    const body = document.body;
    const themeToggle = document.getElementById("themeToggle");
    const icon = themeToggle.querySelector(".toggle-icon");

    if (body.classList.contains("dark-high-contrast")) {
        body.classList.remove("dark-high-contrast");
        themeToggle.classList.remove("dark-high-contrast");
        icon.textContent = "Light";
        localStorage.setItem("theme", "light");
    } else if (body.classList.contains("dark")) {
        body.classList.remove("dark");
        body.classList.add("dark-high-contrast");
        themeToggle.classList.remove("dark");
        themeToggle.classList.add("dark-high-contrast");
        icon.textContent = "HC";
        localStorage.setItem("theme", "dark-high-contrast");
    } else {
        body.classList.add("dark");
        themeToggle.classList.add("dark");
        icon.textContent = "Dark";
        localStorage.setItem("theme", "dark");
    }
}

function initTheme() {
    const savedTheme = localStorage.getItem("theme");
    const themeToggle = document.getElementById("themeToggle");
    if (!themeToggle) return;

    const icon = themeToggle.querySelector(".toggle-icon");

    if (savedTheme === "dark") {
        document.body.classList.add("dark");
        themeToggle.classList.add("dark");
        icon.textContent = "Dark";
    } else if (savedTheme === "dark-high-contrast") {
        document.body.classList.add("dark-high-contrast");
        themeToggle.classList.add("dark-high-contrast");
        icon.textContent = "HC";
    } else {
        icon.textContent = "Light";
    }
}

function difficultyMeta(level) {
    if (level === "Easy") return { label: "Easy", className: "difficulty-easy" };
    if (level === "Medium") return { label: "Medium", className: "difficulty-medium" };
    return { label: "Hard", className: "difficulty-hard" };
}

async function loadProblemSets() {
    const { response, data } = await apiRequest("/problems/");
    if (!response.ok) return;

    problemSets = Array.isArray(data) ? data : [];
    if (!problemSets.length) {
        selectedProblemId = null;
    } else if (!problemSets.some(problem => problem.id === selectedProblemId)) {
        selectedProblemId = problemSets[0].id;
    }

    renderProblemSets();
}

function renderProblemSets() {
    renderProblemList();
    renderSelectedProblem();
    renderSolvedProblems();
}

function renderProblemList() {
    const container = document.getElementById("problemSetList");
    const summary = document.getElementById("problemProgressSummary");
    if (!container || !summary) return;

    if (!problemSets.length) {
        container.innerHTML = `<p class="empty-state">No problems available yet.</p>`;
        summary.innerHTML = "";
        return;
    }

    const solvedCount = problemSets.filter(problem => problem.solved).length;
    summary.innerHTML = `<span class="metric-pill">${solvedCount}/${problemSets.length} solved</span>`;

    container.innerHTML = problemSets.map(problem => {
        const difficulty = difficultyMeta(problem.difficulty);
        return `
            <button class="problem-card ${selectedProblemId === problem.id ? "active-problem" : ""}" onclick="selectProblem(${problem.id})">
                <div class="problem-card-header">
                    <strong>${escapeHtml(problem.title)}</strong>
                    ${problem.solved ? `<span class="status-pill">Solved</span>` : ""}
                </div>
                <p>${escapeHtml(problem.description)}</p>
                <div class="problem-meta-row">
                    <span class="difficulty-pill ${difficulty.className}">${escapeHtml(difficulty.label)}</span>
                    <span class="metric-pill">${problem.points} pts</span>
                </div>
            </button>
        `;
    }).join("");
}

function selectProblem(problemId) {
    selectedProblemId = problemId;
    renderProblemSets();
}

function getSelectedProblem() {
    return problemSets.find(problem => problem.id === selectedProblemId) || null;
}

function renderSelectedProblem() {
    const container = document.getElementById("problemSetDetails");
    const problem = getSelectedProblem();
    if (!container) return;

    if (!problem) {
        container.innerHTML = `<p class="empty-state">Select a problem to start practicing.</p>`;
        return;
    }

    const difficulty = difficultyMeta(problem.difficulty);
    const submission = problem.submission;
    const resultMarkup = submission
        ? `<div class="submission-result ${submission.status === "passed" ? "result-pass" : "result-fail"}">${escapeHtml(String(submission.status).toUpperCase())}: ${escapeHtml(submission.message || "")}</div>`
        : `<p class="empty-state">Submit code to simulate hidden test execution and progress tracking.</p>`;

    const sampleMarkup = problem.sampleTests.map(test => `
        <div class="sample-card">
            <strong>Input</strong>
            <pre>${escapeHtml(test.input)}</pre>
            <strong>Output</strong>
            <pre>${escapeHtml(test.output)}</pre>
        </div>
    `).join("");

    const discussionMarkup = problem.discussions.map(entry => `
        <div class="collab-item">
            <div>
                <strong>${escapeHtml(entry.user)}</strong>
                <p>${escapeHtml(entry.text)}</p>
            </div>
            <button class="ghost-btn" onclick="upvoteProblemDiscussion(${entry.id})">Upvote ${entry.votes}</button>
        </div>
    `).join("");

    const hintMarkup = problem.hints.map(entry => `
        <div class="collab-item">
            <div>
                <strong>${escapeHtml(entry.user)}</strong>
                <p>${escapeHtml(entry.text)}</p>
            </div>
            <button class="ghost-btn" onclick="upvoteProblemHint(${entry.id})">Upvote ${entry.votes}</button>
        </div>
    `).join("");

    const chatMarkup = problem.chat.map(entry => `
        <div class="chat-bubble">
            <strong>${escapeHtml(entry.user)}:</strong> ${escapeHtml(entry.text)}
        </div>
    `).join("");

    container.innerHTML = `
        <div class="problem-header">
            <div>
                <h2>${escapeHtml(problem.title)}</h2>
                <p class="subtitle">${escapeHtml(problem.description)}</p>
            </div>
            <div class="problem-meta-stack">
                <span class="difficulty-pill ${difficulty.className}">${escapeHtml(difficulty.label)}</span>
                <span class="metric-pill">${problem.hiddenTests} hidden tests</span>
            </div>
        </div>

        <div class="problem-spec-grid">
            <div class="info-block">
                <span class="sidebar-note-label">Input Format</span>
                <p>${escapeHtml(problem.inputFormat)}</p>
            </div>
            <div class="info-block">
                <span class="sidebar-note-label">Output Format</span>
                <p>${escapeHtml(problem.outputFormat)}</p>
            </div>
        </div>

        <div class="samples-grid">${sampleMarkup}</div>

        <div class="submission-panel">
            <label for="problemCode">Code Submission</label>
            <textarea id="problemCode" rows="10" placeholder="Paste your function or pseudocode here. Include the core strategy you want checked.">${escapeHtml(submission?.code || "")}</textarea>
            <div class="submission-actions">
                <button onclick="submitProblemSolution(${problem.id})">Submit Code</button>
                <span class="meta">Results are persisted so progress follows your account across devices.</span>
            </div>
            ${resultMarkup}
        </div>

        <div class="collab-grid">
            <div class="collab-panel">
                <div class="card-heading">
                    <div>
                        <p class="eyebrow">Discussion Thread</p>
                        <h3>Ask doubts</h3>
                    </div>
                </div>
                ${discussionMarkup || `<p class="empty-state">No discussion yet.</p>`}
                <textarea id="discussionInput" rows="3" placeholder="Ask a doubt or explain where you are stuck."></textarea>
                <button onclick="addProblemDiscussion(${problem.id})">Post Discussion</button>
            </div>

            <div class="collab-panel">
                <div class="card-heading">
                    <div>
                        <p class="eyebrow">Hint Board</p>
                        <h3>Share hints, not full solutions</h3>
                    </div>
                </div>
                ${hintMarkup || `<p class="empty-state">No hints yet.</p>`}
                <textarea id="hintInput" rows="3" placeholder="Share a nudge without revealing the full answer."></textarea>
                <button onclick="addProblemHint(${problem.id})">Share Hint</button>
            </div>
        </div>

        <div class="collab-panel">
            <div class="card-heading">
                <div>
                    <p class="eyebrow">Problem Chat</p>
                    <h3>Live collaboration</h3>
                </div>
            </div>
            <div class="chat-stack">${chatMarkup || `<p class="empty-state">No chat yet.</p>`}</div>
            <div class="chat-compose">
                <input id="chatInput" type="text" placeholder="Drop a quick message for collaborators.">
                <button onclick="addProblemChat(${problem.id})">Send</button>
            </div>
        </div>
    `;
}

function renderSolvedProblems() {
    const container = document.getElementById("solvedProblemsList");
    if (!container) return;

    const solved = problemSets.filter(problem => problem.solved);
    if (!solved.length) {
        container.innerHTML = `<p class="empty-state">No solved problems yet. Start with an easy one and build momentum.</p>`;
        return;
    }

    container.innerHTML = solved.map(problem => `
        <div class="solved-item">
            <strong>${escapeHtml(problem.title)}</strong>
            <span class="meta">${escapeHtml(problem.difficulty)} · ${problem.points} pts</span>
        </div>
    `).join("");
}

async function submitProblemSolution(problemId) {
    const code = document.getElementById("problemCode")?.value?.trim() || "";
    if (!code) {
        alert("Please add code before submitting.");
        return;
    }

    const { response, data } = await apiRequest(`/problems/${problemId}/submit`, {
        method: "POST",
        body: { code, language: "javascript" }
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to submit problem");
        return;
    }

    await Promise.all([loadProblemSets(), loadNotifications(), loadProfile(), loadLeaderboard()]);
}

async function addProblemDiscussion(problemId) {
    const text = document.getElementById("discussionInput")?.value?.trim();
    if (!text) return;

    const { response, data } = await apiRequest(`/problems/${problemId}/discussions`, {
        method: "POST",
        body: { text }
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to post discussion");
        return;
    }

    await Promise.all([loadProblemSets(), loadNotifications()]);
}

async function addProblemHint(problemId) {
    const text = document.getElementById("hintInput")?.value?.trim();
    if (!text) return;

    const { response, data } = await apiRequest(`/problems/${problemId}/hints`, {
        method: "POST",
        body: { text }
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to post hint");
        return;
    }

    await loadProblemSets();
}

async function addProblemChat(problemId) {
    const input = document.getElementById("chatInput");
    const text = input?.value?.trim();
    if (!text) return;

    const { response, data } = await apiRequest(`/problems/${problemId}/chat`, {
        method: "POST",
        body: { text }
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to send chat message");
        return;
    }

    input.value = "";
    await loadProblemSets();
}

async function upvoteProblemDiscussion(discussionId) {
    await apiRequest(`/problems/discussions/${discussionId}/vote`, {
        method: "POST"
    });
    await loadProblemSets();
}

async function upvoteProblemHint(hintId) {
    await apiRequest(`/problems/hints/${hintId}/vote`, {
        method: "POST"
    });
    await loadProblemSets();
}

async function loadCommunities() {
    const { response, data } = await apiRequest("/communities/");
    if (!response.ok) return;

    communities = Array.isArray(data) ? data : [];
    populateCommunitySelector();
    renderCommunities();
}

function renderCommunities() {
    renderCommunityCatalog();
    renderJoinedCommunityFeed();
}

function renderCommunityCatalog() {
    const container = document.getElementById("communityList");
    if (!container) return;

    if (!communities.length) {
        container.innerHTML = `<p class="empty-state">No communities created yet.</p>`;
        return;
    }

    container.innerHTML = communities.map(community => `
        <article class="community-card">
            <div class="community-card-head">
                <div>
                    <h3>${escapeHtml(community.name)}</h3>
                    <p class="meta">${escapeHtml(community.topic)} · ${community.members} members</p>
                </div>
                <button class="${community.joined ? "ghost-btn" : ""}" onclick="toggleCommunityJoin(${community.id}, ${community.joined})">
                    ${community.joined ? "Joined" : "Join"}
                </button>
            </div>
            <p>${escapeHtml(community.description)}</p>
            <div class="post-footer">
                <span class="tag">${escapeHtml(community.topic)}</span>
                <span class="metric-pill">${community.discussions} discussions</span>
            </div>
            <div class="community-posts-preview">
                ${
                    community.posts.length
                        ? community.posts.map(post => `
                            <div class="community-post-snippet">
                                <strong>${escapeHtml(post.title)}</strong>
                                <p>${escapeHtml(post.excerpt)}</p>
                                <span class="meta">${escapeHtml(post.author)} · ${escapeHtml(post.time)}</span>
                            </div>
                        `).join("")
                        : `<p class="empty-state">No community posts yet.</p>`
                }
            </div>
        </article>
    `).join("");
}

function renderJoinedCommunityFeed() {
    const container = document.getElementById("joinedCommunitiesFeed");
    if (!container) return;

    const joined = communities.filter(community => community.joined);
    if (!joined.length) {
        container.innerHTML = `<p class="empty-state">Join a community to unlock a personalized feed.</p>`;
        return;
    }

    container.innerHTML = joined.map(community => `
        <section class="joined-community-block">
            <div class="card-heading">
                <div>
                    <p class="eyebrow">${escapeHtml(community.topic)}</p>
                    <h3>${escapeHtml(community.name)}</h3>
                </div>
            </div>
            ${
                community.posts.length
                    ? community.posts.map(post => `
                        <div class="community-feed-item">
                            <div>
                                <strong>${escapeHtml(post.title)}</strong>
                                <p>${escapeHtml(post.excerpt)}</p>
                            </div>
                            <span class="meta">${escapeHtml(post.author)} · ${escapeHtml(post.time)}</span>
                        </div>
                    `).join("")
                    : `<p class="empty-state">No posts in this community yet.</p>`
            }
        </section>
    `).join("");
}

async function createCommunity() {
    const name = document.getElementById("communityName")?.value?.trim();
    const topic = document.getElementById("communityTopic")?.value?.trim();
    const description = document.getElementById("communityDescription")?.value?.trim();

    if (!name || !topic || !description) {
        alert("Name, topic, and description are required.");
        return;
    }

    const { response, data } = await apiRequest("/communities/", {
        method: "POST",
        body: { name, topic, description }
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to create community");
        return;
    }

    document.getElementById("communityName").value = "";
    document.getElementById("communityTopic").value = "";
    document.getElementById("communityDescription").value = "";

    await Promise.all([loadCommunities(), loadNotifications(), loadProfile()]);
}

async function toggleCommunityJoin(communityId, isJoined) {
    const { response, data } = await apiRequest(`/communities/${communityId}/join`, {
        method: isJoined ? "DELETE" : "POST"
    });

    if (!response.ok) {
        alert(data?.error || data?.msg || "Unable to update community membership");
        return;
    }

    await Promise.all([loadCommunities(), loadNotifications(), loadProfile()]);
}

function populateCommunitySelector() {
    const select = document.getElementById("postCommunity");
    if (!select) return;

    const previousValue = select.value;
    const options = [`<option value="">Post to main feed</option>`].concat(
        communities
            .filter(community => community.joined)
            .map(community => `<option value="${community.id}">${escapeHtml(community.name)}</option>`)
    );

    select.innerHTML = options.join("");
    if ([...select.options].some(option => option.value === previousValue)) {
        select.value = previousValue;
    }
}

async function loadNotifications() {
    const { response, data } = await apiRequest("/notifications/");
    if (!response.ok) return;
    notifications = Array.isArray(data) ? data : [];
    renderNotifications();
    renderNotificationHistory();
}

function renderNotifications() {
    const container = document.getElementById("notificationCenter");
    if (!container) return;

    if (!notifications.length) {
        container.innerHTML = `<article class="notification-pill"><strong>No new notifications</strong><p>Problem updates, replies, and community activity will appear here.</p></article>`;
        return;
    }

    container.innerHTML = notifications.slice(0, 3).map(item => `
        <article class="notification-pill">
            <strong>${escapeHtml(item.title)}</strong>
            <p>${escapeHtml(item.text)}</p>
            <span class="meta">${escapeHtml(item.time)}</span>
        </article>
    `).join("");
}

function renderNotificationHistory() {
    const container = document.getElementById("notificationHistoryList");
    if (!container) return;

    if (!notifications.length) {
        container.innerHTML = `<p class="empty-state">No notifications yet. Replies, joins, and problem activity will show up here.</p>`;
        return;
    }

    container.innerHTML = notifications.map(item => `
        <article class="notification-pill notification-pill-history">
            <strong>${escapeHtml(item.title)}</strong>
            <p>${escapeHtml(item.text)}</p>
            <span class="meta">${escapeHtml(item.time)}</span>
        </article>
    `).join("");
}

async function initializeNotificationsPage() {
    const token = localStorage.getItem("token");
    if (!token) {
        logout();
        return;
    }

    await loadNotifications();
}

async function initializeDashboard() {
    const { response, data } = await apiRequest("/profile/");
    if (!response.ok) {
        logout();
        return;
    }

    currentProfile = data;
    currentUser = data.username;
    currentUserId = data.user_id;
    currentUserAvatar = data.avatar_url;

    switchSection("feed");
    await Promise.all([
        loadPosts(),
        loadTrending(),
        loadLeaderboard(),
        loadProblemSets(),
        loadCommunities(),
        loadNotifications()
    ]);
}

document.addEventListener("DOMContentLoaded", function() {
    initTheme();
    applySavedSidebarState();

    if (document.getElementById("feedContent")) {
        initializeDashboard().catch(() => logout());
    }

    if (document.getElementById("notificationHistoryList")) {
        initializeNotificationsPage().catch(() => logout());
    }

    window.addEventListener("resize", applySavedSidebarState);
});
