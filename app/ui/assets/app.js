"use strict";

const state = {
  apps: [],
  environments: [],
  builds: [],
  buildConfigs: [],
  imageRepoImages: [],
  imageRepoPage: 1,
  imageRepoPageSize: 10,
  imageRepoTotal: 0,
  imageRepoTotalPages: 0,
  deploymentConfigs: [],
  deployments: [],
  buildWs: null,
  buildWatchTimer: null,
  deployWatchTimer: null,
  imageRepoDeployWatchTimer: null,
};

const byId = (id) => document.getElementById(id);

function showToast(message, typeOrIsError = "success") {
  const toast = byId("toast");
  let level = "success";
  if (typeof typeOrIsError === "boolean") {
    level = typeOrIsError ? "error" : "success";
  } else if (typeof typeOrIsError === "string" && typeOrIsError.trim()) {
    const normalized = typeOrIsError.trim().toLowerCase();
    level = ["success", "error", "warning", "info"].includes(normalized) ? normalized : "success";
  }

  toast.textContent = message;
  toast.classList.remove("success", "error", "warning", "info");
  toast.classList.add(level);
  toast.classList.add("show");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => toast.classList.remove("show"), 2500);
}

async function api(path, options = {}) {
  const opts = { method: "GET", ...options };
  if (opts.body && typeof opts.body !== "string") {
    opts.headers = { ...(opts.headers || {}), "Content-Type": "application/json" };
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data);
    } catch (_) {
      // ignore json parsing failure
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function parseKeyValueLines(text) {
  const result = {};
  const lines = text
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  for (const line of lines) {
    const idx = line.indexOf("=");
    if (idx <= 0) continue;
    const k = line.slice(0, idx).trim();
    const v = line.slice(idx + 1).trim();
    if (k) result[k] = v;
  }
  return result;
}

function parseLineList(text) {
  return text
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
}

function stringifyLineList(items) {
  return (items || []).join("\n");
}

function formatBytes(size) {
  if (size == null || Number.isNaN(Number(size))) return "-";
  const value = Number(size);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let idx = 0;
  let current = value;
  while (current >= 1024 && idx < units.length - 1) {
    current /= 1024;
    idx += 1;
  }
  const fixed = current >= 10 || idx === 0 ? current.toFixed(0) : current.toFixed(1);
  return `${fixed} ${units[idx]}`;
}

function stringifyKeyValueLines(value) {
  const pairs = Object.entries(value || {});
  if (!pairs.length) return "";
  return pairs.map(([k, v]) => `${k}=${v}`).join("\n");
}

function hasWhitespace(text) {
  return /\s/.test(text);
}

function isValidPort(value) {
  return Number.isInteger(value) && value >= 1 && value <= 65535;
}

function statusBadge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setOutput(id, text) {
  byId(id).textContent = text;
}

function appendOutput(id, line) {
  const el = byId(id);
  const merged = el.textContent ? `${el.textContent}\n${line}` : line;
  const lines = merged.split("\n");
  el.textContent = lines.slice(-1000).join("\n");
  el.scrollTop = el.scrollHeight;
}

function setActiveView(name) {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
}

function formatPercent(successCount, totalCount) {
  if (!totalCount) return "0%";
  return `${((successCount / totalCount) * 100).toFixed(1)}%`;
}

function formatDateTime(dateText) {
  if (!dateText) return "--";
  const date = new Date(dateText);
  if (Number.isNaN(date.getTime())) return String(dateText);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function summarizeStatus(items) {
  const summary = { queued: 0, running: 0, success: 0, failed: 0, other: 0 };
  for (const item of items || []) {
    const status = String(item?.status || "").toLowerCase();
    if (Object.prototype.hasOwnProperty.call(summary, status)) {
      summary[status] += 1;
    } else {
      summary.other += 1;
    }
  }
  return summary;
}

function renderStatusChips(containerId, summary) {
  const container = byId(containerId);
  const statusLabel = {
    queued: "排队",
    running: "执行中",
    success: "成功",
    failed: "失败",
    other: "其他",
  };
  const orderedKeys = ["queued", "running", "success", "failed", "other"];
  const chips = orderedKeys
    .filter((key) => (summary[key] || 0) > 0)
    .map((key) => `<span class="status-chip ${key}">${statusLabel[key]}: ${summary[key]}</span>`);
  container.innerHTML = chips.length ? chips.join("") : '<span class="status-chip">暂无数据</span>';
}

function formatBuildSummary(build) {
  if (!build) return "暂无构建记录";
  const appName = state.apps.find((item) => item.id === build.app_id)?.name || `#${build.app_id}`;
  return `#${build.id} | ${appName} | ${build.status} | ${build.image_tag} | ${formatDateTime(build.created_at)}`;
}

function formatDeploySummary(deploy) {
  if (!deploy) return "暂无部署记录";
  const appName = state.apps.find((item) => item.id === deploy.app_id)?.name || `#${deploy.app_id}`;
  const envName = state.environments.find((item) => item.id === deploy.environment_id)?.name || `#${deploy.environment_id}`;
  return `#${deploy.id} | ${appName}/${envName} | ${deploy.status} | ${deploy.mode} | ${formatDateTime(deploy.created_at)}`;
}

function renderMetrics() {
  const buildSummary = summarizeStatus(state.builds);
  const deploySummary = summarizeStatus(state.deployments);

  const buildTotal = state.builds.length;
  const deployTotal = state.deployments.length;
  const pendingTotal = buildSummary.queued + buildSummary.running + deploySummary.queued + deploySummary.running;

  const recentBuild = state.builds[0];
  const recentDeploy = state.deployments[0];

  const latestBuildTime = recentBuild?.created_at ? new Date(recentBuild.created_at).getTime() : 0;
  const latestDeployTime = recentDeploy?.created_at ? new Date(recentDeploy.created_at).getTime() : 0;
  const latestActivity = latestBuildTime >= latestDeployTime ? recentBuild?.created_at : recentDeploy?.created_at;

  byId("metricApps").textContent = String(state.apps.length);
  byId("metricEnvs").textContent = String(state.environments.length);
  byId("metricBuilds").textContent = String(buildTotal);
  byId("metricDeploys").textContent = String(deployTotal);
  byId("metricBuildSuccessRate").textContent = `成功率 ${formatPercent(buildSummary.success, buildTotal)}`;
  byId("metricDeploySuccessRate").textContent = `成功率 ${formatPercent(deploySummary.success, deployTotal)}`;
  byId("metricPendingTasks").textContent = String(pendingTotal);
  byId("metricLastActivity").textContent = formatDateTime(latestActivity);
  byId("metricBuildConfigCount").textContent = String(state.buildConfigs.length);
  byId("metricDeployConfigCount").textContent = String(state.deploymentConfigs.length);

  byId("heroTotalTasks").textContent = String(buildTotal + deployTotal);
  byId("heroBuildSuccessRate").textContent = formatPercent(buildSummary.success, buildTotal);
  byId("heroDeploySuccessRate").textContent = formatPercent(deploySummary.success, deployTotal);
  byId("heroLastRefresh").textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });

  byId("dashboardRecentBuild").textContent = formatBuildSummary(recentBuild);
  byId("dashboardRecentDeploy").textContent = formatDeploySummary(recentDeploy);
  renderStatusChips("dashboardBuildStatusChips", buildSummary);
  renderStatusChips("dashboardDeployStatusChips", deploySummary);
}

function setSelectedBuildConfigId(configId) {
  const value = configId ? String(configId) : "";
  byId("buildConfigIdInput").value = value;
  byId("selectedBuildConfigIdInput").value = value;
}

function setSelectedDeployConfigId(configId) {
  const value = configId ? String(configId) : "";
  byId("deployConfigIdInput").value = value;
  byId("deployConfigSelect").value = value;
}

function setSelectedImageRef(imageRef) {
  byId("selectedImageRefInput").value = imageRef ? String(imageRef) : "";
}

function getBuildPayloadFromForm() {
  const timeoutRaw = byId("buildTimeoutInput").value.trim();
  return {
    app_id: Number(byId("buildAppSelect").value),
    image_tag: byId("buildTagInput").value.trim(),
    context_path: byId("buildContextInput").value.trim() || null,
    build_args: parseKeyValueLines(byId("buildArgsInput").value),
    dockerfile_content: byId("dockerfileInput").value.trim() || null,
    timeout_seconds: timeoutRaw ? Number(timeoutRaw) : null,
  };
}

function getDeployPayloadFromForm() {
  const buildIdRaw = byId("deployBuildIdInput").value.trim();
  const imageRefRaw = byId("deployImageRefInput").value.trim();
  const timeoutRaw = byId("deployTimeoutInput").value.trim();
  return {
    app_id: Number(byId("deployAppSelect").value),
    environment_id: Number(byId("deployEnvSelect").value),
    mode: byId("deployModeSelect").value,
    build_id: buildIdRaw ? Number(buildIdRaw) : null,
    image_ref: imageRefRaw || null,
    container_name: byId("deployContainerNameInput").value.trim() || "app-prod",
    ports: parseLineList(byId("deployPortsInput").value),
    env_vars: parseKeyValueLines(byId("deployEnvVarsInput").value),
    compose_content: byId("deployComposeInput").value.trim() || null,
    remote_dir: byId("deployRemoteDirInput").value.trim() || null,
    timeout_seconds: timeoutRaw ? Number(timeoutRaw) : null,
  };
}

function getImageDeployPayloadFromForm() {
  const timeoutRaw = byId("imageDeployTimeoutInput").value.trim();
  return {
    app_id: Number(byId("imageDeployAppSelect").value),
    environment_id: Number(byId("imageDeployEnvSelect").value),
    image_ref: byId("selectedImageRefInput").value.trim(),
    mode: byId("imageDeployModeSelect").value,
    container_name: byId("imageDeployContainerNameInput").value.trim() || "app-prod",
    ports: parseLineList(byId("imageDeployPortsInput").value),
    env_vars: parseKeyValueLines(byId("imageDeployEnvVarsInput").value),
    compose_content: byId("imageDeployComposeInput").value.trim() || null,
    remote_dir: byId("imageDeployRemoteDirInput").value.trim() || null,
    timeout_seconds: timeoutRaw ? Number(timeoutRaw) : null,
  };
}

function fillBuildFormByConfig(config) {
  byId("buildConfigNameInput").value = config.name || "";
  byId("buildAppSelect").value = String(config.app_id);
  byId("buildTagInput").value = config.image_tag || "";
  byId("buildContextInput").value = config.context_path || "";
  byId("buildArgsInput").value = stringifyKeyValueLines(config.build_args);
  byId("dockerfileInput").value = config.dockerfile_content || "";
  byId("buildTimeoutInput").value = config.timeout_seconds ? String(config.timeout_seconds) : "";
  setSelectedBuildConfigId(config.id);
}

function fillDeployFormByConfig(config) {
  byId("deployConfigNameInput").value = config.name || "";
  byId("deployAppSelect").value = String(config.app_id);
  byId("deployEnvSelect").value = String(config.environment_id);
  byId("deployModeSelect").value = config.mode || "run";
  byId("deployBuildIdInput").value = config.build_id ? String(config.build_id) : "";
  byId("deployImageRefInput").value = config.image_ref || "";
  byId("deployContainerNameInput").value = config.container_name || "app-prod";
  byId("deployPortsInput").value = stringifyLineList(config.ports);
  byId("deployEnvVarsInput").value = stringifyKeyValueLines(config.env_vars);
  byId("deployComposeInput").value = config.compose_content || "";
  byId("deployRemoteDirInput").value = config.remote_dir || "";
  byId("deployTimeoutInput").value = config.timeout_seconds ? String(config.timeout_seconds) : "";
  setSelectedDeployConfigId(config.id);
}

function renderAppTable() {
  const tbody = byId("appsTableBody");
  if (!state.apps.length) {
    tbody.innerHTML = '<tr><td colspan="5">暂无应用</td></tr>';
    return;
  }
  tbody.innerHTML = state.apps
    .map(
      (app) => `<tr data-app-id="${app.id}">
      <td>${app.id}</td>
      <td>${escapeHtml(app.name)}</td>
      <td>${escapeHtml(app.description || "-")}</td>
      <td>${escapeHtml(app.created_at)}</td>
      <td>
        <button type="button" class="ghost-btn app-edit-btn" data-app-id="${app.id}">编辑</button>
        <button type="button" class="ghost-btn app-delete-btn" data-app-id="${app.id}">删除</button>
      </td>
    </tr>`
    )
    .join("");

  tbody.querySelectorAll(".app-edit-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const appId = Number(btn.dataset.appId);
      const app = state.apps.find((x) => x.id === appId);
      if (!app) return;

      const nameInput = window.prompt("请输入新的应用名称（不允许空格）", app.name);
      if (nameInput === null) return;
      const newName = nameInput.trim();
      if (!newName) {
        showToast("应用名称不能为空", true);
        return;
      }
      if (hasWhitespace(newName)) {
        showToast("应用名称不允许包含空格", true);
        return;
      }

      const descInput = window.prompt("请输入新的描述（可留空）", app.description || "");
      if (descInput === null) return;
      const newDesc = descInput.trim();

      try {
        await api(`/api/apps/${appId}`, {
          method: "PUT",
          body: { name: newName, description: newDesc || null },
        });
        await loadApps();
        showToast(`应用 #${appId} 已更新`);
      } catch (error) {
        showToast(`更新应用失败: ${error.message}`, true);
      }
    });
  });

  tbody.querySelectorAll(".app-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const appId = Number(btn.dataset.appId);
      const app = state.apps.find((x) => x.id === appId);
      if (!app) return;

      const ok = window.confirm(`确认删除应用 ${app.name} (#${appId})？`);
      if (!ok) return;

      try {
        await api(`/api/apps/${appId}`, { method: "DELETE" });
        await loadApps();
        showToast(`应用 #${appId} 已删除`);
      } catch (error) {
        showToast(`删除应用失败: ${error.message}`, true);
      }
    });
  });
}

function renderEnvironmentTable() {
  const tbody = byId("envTableBody");
  if (!state.environments.length) {
    tbody.innerHTML = '<tr><td colspan="7">暂无环境</td></tr>';
    return;
  }
  tbody.innerHTML = state.environments
    .map(
      (env) => `<tr data-env-id="${env.id}">
      <td>${env.id}</td>
      <td>${escapeHtml(env.name)}</td>
      <td>${escapeHtml(env.host)}</td>
      <td>${env.port}</td>
      <td>${escapeHtml(env.username)}</td>
      <td>用户名 + 密码</td>
      <td>
        <button type="button" class="ghost-btn env-row-test-btn" data-env-id="${env.id}">测试</button>
        <button type="button" class="ghost-btn env-row-edit-btn" data-env-id="${env.id}">编辑</button>
        <button type="button" class="ghost-btn env-row-delete-btn" data-env-id="${env.id}">删除</button>
      </td>
    </tr>`
    )
    .join("");

  tbody.querySelectorAll(".env-row-test-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const envId = Number(btn.dataset.envId);
      if (!envId) return;
      setOutput("envTestOut", `测试环境 #${envId} 连接中...`);
      try {
        const data = await api(`/api/environments/${envId}/test-connection`, { method: "POST" });
        setOutput("envTestOut", `env_id=${envId}\nok=${data.ok}\ndetail=${data.detail}`);
        showToast(data.ok ? `环境 #${envId} 连接成功` : `环境 #${envId} 连接失败`, !data.ok);
      } catch (error) {
        setOutput("envTestOut", `env_id=${envId}\n执行失败: ${error.message}`);
        showToast(`环境连接测试失败: ${error.message}`, true);
      }
    });
  });

  tbody.querySelectorAll(".env-row-edit-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const envId = Number(btn.dataset.envId);
      const env = state.environments.find((item) => item.id === envId);
      if (!env) return;

      const nameInput = window.prompt("请输入新的环境名称", env.name);
      if (nameInput === null) return;
      const hostInput = window.prompt("请输入新的 Host", env.host);
      if (hostInput === null) return;
      const portInput = window.prompt("请输入新的端口", String(env.port));
      if (portInput === null) return;
      const usernameInput = window.prompt("请输入新的用户名", env.username);
      if (usernameInput === null) return;
      const passwordInput = window.prompt("请输入新的密码（留空表示保持不变）", "");
      if (passwordInput === null) return;

      const newName = nameInput.trim();
      const newHost = hostInput.trim();
      const newPort = Number(portInput.trim());
      const newUsername = usernameInput.trim();

      if (!newName || !newHost || !newUsername) {
        showToast("环境名称、Host、用户名不能为空", true);
        return;
      }
      if (!isValidPort(newPort)) {
        showToast("端口必须是 1-65535 的整数", true);
        return;
      }

      const body = {
        name: newName,
        host: newHost,
        port: newPort,
        username: newUsername,
      };
      if (passwordInput.trim()) {
        body.password = passwordInput;
      }

      try {
        await api(`/api/environments/${envId}`, {
          method: "PUT",
          body,
        });
        await loadEnvironments();
        showToast(`环境 #${envId} 已更新`);
      } catch (error) {
        showToast(`更新环境失败: ${error.message}`, true);
      }
    });
  });

  tbody.querySelectorAll(".env-row-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const envId = Number(btn.dataset.envId);
      const env = state.environments.find((item) => item.id === envId);
      if (!env) return;

      const ok = window.confirm(`确认删除环境 ${env.name} (${env.host}) #${envId}？`);
      if (!ok) return;

      try {
        await api(`/api/environments/${envId}`, { method: "DELETE" });
        await loadEnvironments();
        showToast(`环境 #${envId} 已删除`);
      } catch (error) {
        showToast(`删除环境失败: ${error.message}`, true);
      }
    });
  });
}

function renderBuildConfigTable() {
  const tbody = byId("buildConfigsTableBody");
  if (!state.buildConfigs.length) {
    tbody.innerHTML = '<tr><td colspan="6">暂无构建配置</td></tr>';
    return;
  }

  tbody.innerHTML = state.buildConfigs
    .map((config) => {
      const appName = state.apps.find((item) => item.id === config.app_id)?.name || `#${config.app_id}`;
      return `<tr data-config-id="${config.id}">
      <td>${config.id}</td>
      <td>${escapeHtml(config.name)}</td>
      <td>${escapeHtml(appName)}</td>
      <td>${escapeHtml(config.image_tag)}</td>
      <td>${escapeHtml(config.updated_at)}</td>
      <td>
        <button type="button" class="ghost-btn build-config-load-btn" data-config-id="${config.id}">加载</button>
        <button type="button" class="ghost-btn build-config-run-btn" data-config-id="${config.id}">运行</button>
        <button type="button" class="ghost-btn build-config-delete-btn" data-config-id="${config.id}">删除</button>
      </td>
    </tr>`;
    })
    .join("");

  tbody.querySelectorAll(".build-config-load-btn").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      const configId = Number(btn.dataset.configId);
      const config = state.buildConfigs.find((item) => item.id === configId);
      if (!config) return;
      fillBuildFormByConfig(config);
      showToast(`已加载配置 #${configId}`);
    });
  });

  tbody.querySelectorAll("tr[data-config-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const configId = Number(row.dataset.configId);
      if (!configId) return;
      setSelectedBuildConfigId(configId);
    });
  });

  tbody.querySelectorAll(".build-config-run-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const configId = Number(btn.dataset.configId);
      if (!configId) return;
      await runBuildConfig(configId);
    });
  });

  tbody.querySelectorAll(".build-config-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const configId = Number(btn.dataset.configId);
      if (!configId) return;
      await deleteBuildConfig(configId);
    });
  });
}

function renderBuildTable() {
  const tbody = byId("buildsTableBody");
  if (!state.builds.length) {
    tbody.innerHTML = '<tr><td colspan="5">暂无构建任务</td></tr>';
    return;
  }
  tbody.innerHTML = state.builds
    .map(
      (build) => `<tr data-build-id="${build.id}">
      <td>${build.id}</td>
      <td>${build.app_id}</td>
      <td>${escapeHtml(build.image_tag)}</td>
      <td>${statusBadge(build.status)}</td>
      <td>${escapeHtml(build.image_digest || "-")}</td>
    </tr>`
    )
    .join("");
  tbody.querySelectorAll("tr[data-build-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const buildId = Number(row.dataset.buildId);
      byId("selectedBuildIdInput").value = String(buildId);
      watchBuild(buildId);
    });
  });
}

function renderImageRepoPagination(extraHint = "") {
  const total = state.imageRepoTotal;
  const page = state.imageRepoPage;
  const pageSize = state.imageRepoPageSize;
  const totalPages = state.imageRepoTotalPages;

  const pageInfo = byId("imageRepoPageInfo");
  const prevBtn = byId("imageRepoPrevBtn");
  const nextBtn = byId("imageRepoNextBtn");
  const pageSizeSelect = byId("imageRepoPageSizeSelect");

  let text = `第 ${page}/${totalPages || 0} 页 · ${total} 条`;
  if (total > 0 && totalPages > 0) {
    const start = (page - 1) * pageSize + 1;
    const end = Math.min(page * pageSize, total);
    text = `第 ${page}/${totalPages} 页 · ${start}-${end} / ${total}`;
  }
  if (extraHint) {
    text = `${text} · ${extraHint}`;
  }

  pageInfo.textContent = text;
  prevBtn.disabled = page <= 1;
  nextBtn.disabled = totalPages <= 0 || page >= totalPages;
  pageSizeSelect.value = String(pageSize);
}

function renderImageRepoTable(errorText = "") {
  const tbody = byId("imageRepoTableBody");
  if (errorText) {
    tbody.innerHTML = `<tr><td colspan="6">${escapeHtml(errorText)}</td></tr>`;
    renderImageRepoPagination("加载失败");
    return;
  }
  if (!state.imageRepoImages.length) {
    tbody.innerHTML = '<tr><td colspan="6">暂无本地镜像</td></tr>';
    renderImageRepoPagination();
    return;
  }

  tbody.innerHTML = state.imageRepoImages
    .map((image) => {
      const rowSelected = byId("selectedImageRefInput").value === image.image_ref ? "selected" : "";
      return `<tr data-image-ref="${escapeHtml(image.image_ref)}" class="${rowSelected}">
      <td>${escapeHtml(image.repository)}</td>
      <td>${escapeHtml(image.tag)}</td>
      <td>${escapeHtml(image.image_id)}</td>
      <td>${escapeHtml(image.digest || "-")}</td>
      <td>${escapeHtml(formatDateTime(image.created_at))}</td>
      <td>${escapeHtml(formatBytes(image.size_bytes))}</td>
    </tr>`;
    })
    .join("");

  tbody.querySelectorAll("tr[data-image-ref]").forEach((row) => {
    row.addEventListener("click", () => {
      const imageRef = row.dataset.imageRef;
      if (!imageRef) return;
      setSelectedImageRef(imageRef);
      renderImageRepoTable();
      showToast(`已选择镜像 ${imageRef}`, "info");
    });
  });
  renderImageRepoPagination();
}

function renderDeploymentTable() {
  const tbody = byId("deploysTableBody");
  if (!state.deployments.length) {
    tbody.innerHTML = '<tr><td colspan="7">暂无部署任务</td></tr>';
    return;
  }
  tbody.innerHTML = state.deployments
    .map((deploy) => {
      const appName = state.apps.find((item) => item.id === deploy.app_id)?.name || `#${deploy.app_id}`;
      const envName = state.environments.find((item) => item.id === deploy.environment_id)?.name || `#${deploy.environment_id}`;
      return `<tr data-deploy-id="${deploy.id}">
      <td>${deploy.id}</td>
      <td>${escapeHtml(appName)}</td>
      <td>${escapeHtml(envName)}</td>
      <td>${escapeHtml(deploy.mode)}</td>
      <td>${statusBadge(deploy.status)}</td>
      <td>${escapeHtml(deploy.created_at)}</td>
      <td>
        <button type="button" class="ghost-btn deploy-detail-btn" data-deploy-id="${deploy.id}">详情</button>
        <button type="button" class="ghost-btn deploy-log-btn" data-deploy-id="${deploy.id}">日志</button>
      </td>
    </tr>`;
    })
    .join("");

  tbody.querySelectorAll("tr[data-deploy-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const deployId = Number(row.dataset.deployId);
      if (!deployId) return;
      byId("selectedDeployIdInput").value = String(deployId);
      viewDeploymentDetail(deployId);
    });
  });

  tbody.querySelectorAll(".deploy-detail-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const deployId = Number(btn.dataset.deployId);
      if (!deployId) return;
      byId("selectedDeployIdInput").value = String(deployId);
      await viewDeploymentDetail(deployId);
    });
  });

  tbody.querySelectorAll(".deploy-log-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const deployId = Number(btn.dataset.deployId);
      if (!deployId) return;
      byId("selectedDeployIdInput").value = String(deployId);
      await watchDeployment(deployId);
    });
  });
}

function renderDeploymentConfigSelect() {
  const select = byId("deployConfigSelect");
  const currentValue = byId("deployConfigIdInput").value;
  if (!state.deploymentConfigs.length) {
    select.innerHTML = '<option value="">暂无部署配置</option>';
    if (currentValue) {
      setSelectedDeployConfigId(null);
    }
    return;
  }

  const options = state.deploymentConfigs
    .map((config) => {
      const appName = state.apps.find((item) => item.id === config.app_id)?.name || `#${config.app_id}`;
      const envName = state.environments.find((item) => item.id === config.environment_id)?.name || `#${config.environment_id}`;
      const label = `${config.name} | ${appName}/${envName} | ${config.mode}`;
      return `<option value="${config.id}">${escapeHtml(label)}</option>`;
    })
    .join("");
  select.innerHTML = `<option value="">请选择已保存部署配置</option>${options}`;

  const selectedExists =
    currentValue && state.deploymentConfigs.some((config) => String(config.id) === String(currentValue));
  if (selectedExists) {
    select.value = String(currentValue);
  } else {
    setSelectedDeployConfigId(null);
  }
}

function renderSelectOptions() {
  const appOptions = state.apps.map((app) => `<option value="${app.id}">${escapeHtml(app.name)} (#${app.id})</option>`).join("");
  const envOptions = state.environments
    .map((env) => `<option value="${env.id}">${escapeHtml(env.name)} (${escapeHtml(env.host)})</option>`)
    .join("");

  byId("buildAppSelect").innerHTML = appOptions;
  byId("deployAppSelect").innerHTML = appOptions;
  byId("imageDeployAppSelect").innerHTML = appOptions;
  byId("deployEnvSelect").innerHTML = envOptions;
  byId("imageDeployEnvSelect").innerHTML = envOptions;
  byId("remoteEnvSelect").innerHTML = envOptions;
  renderDeploymentConfigSelect();
}

async function loadApps() {
  state.apps = await api("/api/apps");
  renderAppTable();
  renderSelectOptions();
  if (state.buildConfigs.length) {
    renderBuildConfigTable();
  }
  renderMetrics();
}

async function loadEnvironments() {
  state.environments = await api("/api/environments");
  renderEnvironmentTable();
  renderSelectOptions();
  renderMetrics();
}

async function loadBuilds() {
  state.builds = await api("/api/builds?limit=200");
  renderBuildTable();
  renderMetrics();
}

async function loadBuildConfigs() {
  state.buildConfigs = await api("/api/build-configs?limit=200");
  renderBuildConfigTable();
  renderMetrics();
}

async function loadImageRepoImages() {
  try {
    const data = await api(
      `/api/image-repo/images?page=${state.imageRepoPage}&page_size=${state.imageRepoPageSize}`
    );
    state.imageRepoImages = data.items || [];
    state.imageRepoTotal = Number(data.total || 0);
    state.imageRepoTotalPages = Number(data.total_pages || 0);
    if (state.imageRepoTotalPages > 0 && state.imageRepoPage > state.imageRepoTotalPages) {
      state.imageRepoPage = state.imageRepoTotalPages;
      return await loadImageRepoImages();
    }
    renderImageRepoTable();
  } catch (error) {
    state.imageRepoImages = [];
    state.imageRepoTotal = 0;
    state.imageRepoTotalPages = 0;
    renderImageRepoTable(`镜像列表加载失败: ${error.message}`);
    showToast(`镜像列表加载失败: ${error.message}`, "warning");
  }
}

async function loadDeploymentConfigs() {
  state.deploymentConfigs = await api("/api/deploy-configs?limit=200");
  renderDeploymentConfigSelect();
  renderMetrics();
}

async function loadDeployments() {
  state.deployments = await api("/api/deploy?limit=200");
  renderDeploymentTable();
  renderMetrics();
}

async function loadAll() {
  try {
    await Promise.all([
      loadApps(),
      loadEnvironments(),
      loadBuilds(),
      loadBuildConfigs(),
      loadImageRepoImages(),
      loadDeploymentConfigs(),
      loadDeployments(),
    ]);
  } catch (error) {
    showToast(`加载失败: ${error.message}`, true);
  }
}

function closeBuildWatch() {
  if (state.buildWs) {
    state.buildWs.close();
    state.buildWs = null;
  }
  if (state.buildWatchTimer) {
    window.clearInterval(state.buildWatchTimer);
    state.buildWatchTimer = null;
  }
}

function closeDeployWatch() {
  if (state.deployWatchTimer) {
    window.clearInterval(state.deployWatchTimer);
    state.deployWatchTimer = null;
  }
}

async function watchBuild(buildId) {
  closeBuildWatch();
  setOutput("buildLogsOut", `加载 Build #${buildId} 日志中...`);
  try {
    const [logs, detail] = await Promise.all([
      api(`/api/builds/${buildId}/logs?tail=300`),
      api(`/api/builds/${buildId}`),
    ]);
    const head = `Build #${buildId} | status=${detail.status} | tag=${detail.image_tag}\n`;
    setOutput("buildLogsOut", `${head}${(logs.lines || []).join("\n") || "(暂无日志)"}`);
  } catch (error) {
    setOutput("buildLogsOut", `读取构建日志失败: ${error.message}`);
    return;
  }

  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${scheme}://${window.location.host}/api/builds/ws/${buildId}/logs`);
  state.buildWs = ws;
  ws.onmessage = (evt) => {
    if (evt.data !== "heartbeat") {
      appendOutput("buildLogsOut", evt.data);
    }
  };
  ws.onerror = () => {
    appendOutput("buildLogsOut", "[ws] 日志流连接出现错误，已切换轮询");
  };

  state.buildWatchTimer = window.setInterval(async () => {
    try {
      const detail = await api(`/api/builds/${buildId}`);
      if (detail.status === "success" || detail.status === "failed") {
        appendOutput("buildLogsOut", `[status] ${detail.status}`);
        await loadBuilds();
      }
    } catch (_) {
      // ignore periodic detail failures
    }
  }, 4000);
}

async function runBuildConfig(configId) {
  try {
    const build = await api(`/api/build-configs/${configId}/run`, { method: "POST" });
    byId("selectedBuildIdInput").value = String(build.id);
    await loadBuilds();
    showToast(`配置 #${configId} 已触发构建 #${build.id}`);
    await watchBuild(build.id);
  } catch (error) {
    showToast(`运行配置失败: ${error.message}`, true);
  }
}

async function deleteBuildConfig(configId) {
  const config = state.buildConfigs.find((item) => item.id === configId);
  const ok = window.confirm(`确认删除构建配置 ${config?.name || configId} (#${configId})？`);
  if (!ok) return;
  try {
    await api(`/api/build-configs/${configId}`, { method: "DELETE" });
    if (String(configId) === byId("buildConfigIdInput").value) {
      setSelectedBuildConfigId(null);
    }
    await loadBuildConfigs();
    showToast(`配置 #${configId} 已删除`);
  } catch (error) {
    showToast(`删除配置失败: ${error.message}`, true);
  }
}

function formatDeploymentDetailText(detail) {
  const appName = state.apps.find((item) => item.id === detail.app_id)?.name || `#${detail.app_id}`;
  const envName = state.environments.find((item) => item.id === detail.environment_id)?.name || `#${detail.environment_id}`;
  const lines = [
    `Deploy #${detail.id}`,
    `状态: ${detail.status}`,
    `模式: ${detail.mode}`,
    `应用: ${appName} (#${detail.app_id})`,
    `环境: ${envName} (#${detail.environment_id})`,
    `镜像 Digest: ${detail.image_digest || "-"}`,
    `创建时间: ${detail.created_at}`,
    `日志文件: ${detail.log_file}`,
  ];
  if (detail.error_message) {
    lines.push(`错误信息: ${detail.error_message}`);
  }
  return lines.join("\n");
}

function renderDeploymentDetail(detail) {
  setOutput("deployDetailOut", formatDeploymentDetailText(detail));
}

function renderImageDeploymentDetail(detail) {
  setOutput("imageDeployDetailOut", formatDeploymentDetailText(detail));
}

async function viewDeploymentDetail(deployId) {
  try {
    const detail = await api(`/api/deploy/${deployId}`);
    renderDeploymentDetail(detail);
  } catch (error) {
    setOutput("deployDetailOut", `读取部署详情失败: ${error.message}`);
  }
}

function validateDeployConfigPayload(payload) {
  if (!payload.app_id || !payload.environment_id) {
    return "请选择应用和环境";
  }
  if (!payload.mode) {
    return "请选择部署模式";
  }
  if (!payload.build_id && !payload.image_ref) {
    return "Build ID 和镜像引用至少填写一个";
  }
  return null;
}

async function deleteDeploymentConfig(configId) {
  const config = state.deploymentConfigs.find((item) => item.id === configId);
  const ok = window.confirm(`确认删除部署配置 ${config?.name || configId} (#${configId})？`);
  if (!ok) return;
  try {
    await api(`/api/deploy-configs/${configId}`, { method: "DELETE" });
    if (String(configId) === byId("deployConfigIdInput").value) {
      setSelectedDeployConfigId(null);
      byId("deployConfigNameInput").value = "";
    }
    await loadDeploymentConfigs();
    showToast(`部署配置 #${configId} 已删除`);
  } catch (error) {
    showToast(`删除部署配置失败: ${error.message}`, true);
  }
}

async function watchDeployment(deployId) {
  closeDeployWatch();
  setOutput("deployLogsOut", `加载 Deploy #${deployId} 日志中...`);

  const refresh = async () => {
    try {
      const [logs, detail] = await Promise.all([
        api(`/api/deploy/${deployId}/logs?tail=300`),
        api(`/api/deploy/${deployId}`),
      ]);
      renderDeploymentDetail(detail);
      const head = `Deploy #${deployId} | status=${detail.status} | mode=${detail.mode}\n`;
      setOutput("deployLogsOut", `${head}${(logs.lines || []).join("\n") || "(暂无日志)"}`);
      if (detail.status === "success" || detail.status === "failed") {
        await loadDeployments();
      }
    } catch (error) {
      setOutput("deployLogsOut", `读取部署日志失败: ${error.message}`);
    }
  };

  await refresh();
  state.deployWatchTimer = window.setInterval(refresh, 4000);
}

function closeImageRepoDeployWatch() {
  if (state.imageRepoDeployWatchTimer) {
    window.clearInterval(state.imageRepoDeployWatchTimer);
    state.imageRepoDeployWatchTimer = null;
  }
}

async function watchImageRepoDeployment(deployId) {
  closeImageRepoDeployWatch();
  setOutput("imageDeployLogsOut", `加载 Deploy #${deployId} 日志中...`);

  const refresh = async () => {
    try {
      const [logs, detail] = await Promise.all([
        api(`/api/deploy/${deployId}/logs?tail=300`),
        api(`/api/deploy/${deployId}`),
      ]);
      renderImageDeploymentDetail(detail);
      const head = `Deploy #${deployId} | status=${detail.status} | mode=${detail.mode}\n`;
      setOutput("imageDeployLogsOut", `${head}${(logs.lines || []).join("\n") || "(暂无日志)"}`);
      if (detail.status === "success" || detail.status === "failed") {
        await loadDeployments();
      }
    } catch (error) {
      setOutput("imageDeployLogsOut", `读取部署日志失败: ${error.message}`);
    }
  };

  await refresh();
  state.imageRepoDeployWatchTimer = window.setInterval(refresh, 4000);
}

function precheckNameLabel(name) {
  const mapping = {
    docker_daemon: "Docker Daemon",
    docker_version: "Docker 版本",
    disk_space: "磁盘空间",
    builder_cache: "构建缓存",
    docker_socket_permission: "Docker Socket 权限",
    ssh_connection: "SSH 连接",
    docker_available: "远程 Docker",
    compose_available: "远程 Compose",
    environment: "环境配置",
    ssh_password: "SSH 密码",
  };
  return mapping[name] || name;
}

function formatPrecheckResult(data) {
  const lines = [`overall: ${data.ok ? "PASS" : "FAIL"}`];
  for (const item of data.items || []) {
    lines.push(`- ${item.name}: ${item.ok ? "OK" : "FAIL"} | ${item.detail}`);
  }
  return lines.join("\n");
}

function renderPrecheckVisual(scope, data, extraSummary = "") {
  const badge = byId(`${scope}PrecheckStatusBadge`);
  const summary = byId(`${scope}PrecheckSummaryText`);
  const itemsContainer = byId(`${scope}PrecheckItems`);

  const total = (data.items || []).length;
  const passCount = (data.items || []).filter((item) => item.ok).length;
  badge.className = `precheck-badge ${data.ok ? "pass" : "fail"}`;
  badge.textContent = data.ok ? "通过" : "失败";

  const detailSummary = total ? `${passCount}/${total} 项通过` : "无检查项";
  summary.textContent = extraSummary ? `${detailSummary} | ${extraSummary}` : detailSummary;

  if (!total) {
    itemsContainer.innerHTML = '<article class="check-item muted"><h4>无检查项</h4><p>未返回可展示的检查结果。</p></article>';
    return;
  }

  itemsContainer.innerHTML = data.items
    .map((item) => {
      const cls = item.ok ? "ok" : "fail";
      return `<article class="check-item ${cls}">
        <h4>${escapeHtml(precheckNameLabel(item.name))}</h4>
        <p>${escapeHtml(item.detail || "")}</p>
      </article>`;
    })
    .join("");
}

function renderPrecheckLoading(scope, text) {
  const badge = byId(`${scope}PrecheckStatusBadge`);
  const summary = byId(`${scope}PrecheckSummaryText`);
  const itemsContainer = byId(`${scope}PrecheckItems`);
  badge.className = "precheck-badge pending";
  badge.textContent = "检查中";
  summary.textContent = text;
  itemsContainer.innerHTML = '<article class="check-item muted"><h4>执行中</h4><p>正在采集检查数据，请稍候...</p></article>';
}

function bindNavigation() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => setActiveView(btn.dataset.view));
  });
}

function bindForms() {
  byId("appForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const appName = byId("appNameInput").value.trim();
    if (!appName) {
      showToast("应用名称不能为空", true);
      return;
    }
    if (hasWhitespace(appName)) {
      showToast("应用名称不允许包含空格", true);
      return;
    }
    const payload = {
      name: appName,
      description: byId("appDescInput").value.trim() || null,
    };
    try {
      await api("/api/apps", { method: "POST", body: payload });
      byId("appForm").reset();
      await loadApps();
      showToast("应用创建成功");
    } catch (error) {
      showToast(`创建应用失败: ${error.message}`, true);
    }
  });

  byId("envForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      name: byId("envNameInput").value.trim(),
      host: byId("envHostInput").value.trim(),
      port: Number(byId("envPortInput").value || "22"),
      username: byId("envUserInput").value.trim(),
      password: byId("envPasswordInput").value,
    };
    try {
      await api("/api/environments", { method: "POST", body: payload });
      byId("envForm").reset();
      byId("envPortInput").value = "22";
      await loadEnvironments();
      showToast("环境创建成功");
    } catch (error) {
      showToast(`创建环境失败: ${error.message}`, true);
    }
  });

  byId("buildForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = getBuildPayloadFromForm();
    if (!payload.app_id || !payload.image_tag) {
      showToast("请填写应用和镜像 Tag", true);
      return;
    }
    try {
      const data = await api("/api/builds", { method: "POST", body: payload });
      byId("selectedBuildIdInput").value = String(data.id);
      await loadBuilds();
      showToast(`构建已提交 #${data.id}`);
      await watchBuild(data.id);
    } catch (error) {
      showToast(`提交构建失败: ${error.message}`, true);
    }
  });

  byId("deployForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const configId = Number(byId("deployConfigSelect").value);
    if (!configId) {
      showToast("请先从下拉框选择已保存部署配置，再提交部署", true);
      return;
    }
    try {
      const data = await api(`/api/deploy-configs/${configId}/run`, { method: "POST" });
      byId("selectedDeployIdInput").value = String(data.id);
      await loadDeployments();
      showToast(`已按配置 #${configId} 提交部署 #${data.id}`);
      await watchDeployment(data.id);
    } catch (error) {
      showToast(`提交部署失败: ${error.message}`, true);
    }
  });

  byId("imageDeployForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = getImageDeployPayloadFromForm();
    if (!payload.image_ref) {
      showToast("请先在镜像列表中选择镜像", true);
      return;
    }
    if (!payload.app_id || !payload.environment_id) {
      showToast("请选择应用和部署环境", true);
      return;
    }

    setOutput("imageDeployPrecheckOut", "远程预检执行中...");
    setOutput("imageDeployDetailOut", "部署任务创建中...");
    setOutput("imageDeployLogsOut", "等待部署日志...");

    try {
      const data = await api("/api/image-repo/deploy", { method: "POST", body: payload });
      setOutput("imageDeployPrecheckOut", formatPrecheckResult(data.precheck));
      byId("selectedDeployIdInput").value = String(data.deployment.id);
      await loadDeployments();
      showToast(`镜像部署任务已提交 #${data.deployment.id}`);
      await watchImageRepoDeployment(data.deployment.id);
    } catch (error) {
      setOutput("imageDeployPrecheckOut", `预检或部署创建失败: ${error.message}`);
      setOutput("imageDeployDetailOut", "部署未执行");
      setOutput("imageDeployLogsOut", "无可用日志");
      showToast(`镜像部署失败: ${error.message}`, true);
    }
  });
}

function bindActions() {
  byId("refreshAllBtn").addEventListener("click", async () => {
    await loadAll();
    showToast("已刷新");
  });
  byId("refreshBuildsBtn").addEventListener("click", loadBuilds);
  byId("refreshBuildConfigsBtn").addEventListener("click", loadBuildConfigs);
  byId("refreshImageRepoBtn").addEventListener("click", async () => {
    state.imageRepoPage = 1;
    await loadImageRepoImages();
  });
  byId("refreshDeployConfigsBtn").addEventListener("click", loadDeploymentConfigs);
  byId("refreshDeploysBtn").addEventListener("click", loadDeployments);

  byId("imageRepoPageSizeSelect").addEventListener("change", async () => {
    const size = Number(byId("imageRepoPageSizeSelect").value);
    if (!size || size <= 0) return;
    state.imageRepoPageSize = size;
    state.imageRepoPage = 1;
    await loadImageRepoImages();
  });

  byId("imageRepoPrevBtn").addEventListener("click", async () => {
    if (state.imageRepoPage <= 1) return;
    state.imageRepoPage -= 1;
    await loadImageRepoImages();
  });

  byId("imageRepoNextBtn").addEventListener("click", async () => {
    if (state.imageRepoTotalPages <= 0 || state.imageRepoPage >= state.imageRepoTotalPages) return;
    state.imageRepoPage += 1;
    await loadImageRepoImages();
  });

  byId("watchBuildBtn").addEventListener("click", async () => {
    const buildId = Number(byId("selectedBuildIdInput").value);
    if (!buildId) {
      showToast("请输入 Build ID", true);
      return;
    }
    await watchBuild(buildId);
  });

  byId("runBuildConfigBtn").addEventListener("click", async () => {
    const configId = Number(byId("selectedBuildConfigIdInput").value);
    if (!configId) {
      showToast("请先选择构建配置", true);
      return;
    }
    await runBuildConfig(configId);
  });

  byId("deleteBuildConfigBtn").addEventListener("click", async () => {
    const configId = Number(byId("selectedBuildConfigIdInput").value);
    if (!configId) {
      showToast("请先选择构建配置", true);
      return;
    }
    await deleteBuildConfig(configId);
  });

  byId("saveBuildConfigBtn").addEventListener("click", async () => {
    const configName = byId("buildConfigNameInput").value.trim();
    if (!configName) {
      showToast("保存配置时请填写配置名称", true);
      return;
    }
    const buildPayload = getBuildPayloadFromForm();
    if (!buildPayload.app_id || !buildPayload.image_tag) {
      showToast("请先填写应用和镜像 Tag", true);
      return;
    }
    try {
      const config = await api("/api/build-configs", {
        method: "POST",
        body: {
          name: configName,
          app_id: buildPayload.app_id,
          image_tag: buildPayload.image_tag,
          context_path: buildPayload.context_path,
          dockerfile_content: buildPayload.dockerfile_content,
          build_args: buildPayload.build_args,
          timeout_seconds: buildPayload.timeout_seconds,
        },
      });
      setSelectedBuildConfigId(config.id);
      await loadBuildConfigs();
      showToast(`构建配置已保存 #${config.id}`);
    } catch (error) {
      showToast(`保存配置失败: ${error.message}`, true);
    }
  });

  byId("updateBuildConfigBtn").addEventListener("click", async () => {
    const configId = Number(byId("buildConfigIdInput").value);
    if (!configId) {
      showToast("请先选择配置再更新", true);
      return;
    }
    const configName = byId("buildConfigNameInput").value.trim();
    if (!configName) {
      showToast("更新配置时请填写配置名称", true);
      return;
    }
    const buildPayload = getBuildPayloadFromForm();
    if (!buildPayload.app_id || !buildPayload.image_tag) {
      showToast("请先填写应用和镜像 Tag", true);
      return;
    }
    try {
      const config = await api(`/api/build-configs/${configId}`, {
        method: "PUT",
        body: {
          name: configName,
          app_id: buildPayload.app_id,
          image_tag: buildPayload.image_tag,
          context_path: buildPayload.context_path,
          dockerfile_content: buildPayload.dockerfile_content,
          build_args: buildPayload.build_args,
          timeout_seconds: buildPayload.timeout_seconds,
        },
      });
      setSelectedBuildConfigId(config.id);
      await loadBuildConfigs();
      showToast(`构建配置已更新 #${config.id}`);
    } catch (error) {
      showToast(`更新配置失败: ${error.message}`, true);
    }
  });

  byId("clearBuildConfigSelectionBtn").addEventListener("click", () => {
    setSelectedBuildConfigId(null);
    byId("buildConfigNameInput").value = "";
    showToast("已清空配置选择");
  });

  byId("deployConfigSelect").addEventListener("change", () => {
    const configId = Number(byId("deployConfigSelect").value);
    setSelectedDeployConfigId(configId || null);
  });

  byId("loadDeployConfigBtn").addEventListener("click", () => {
    const configId = Number(byId("deployConfigSelect").value);
    if (!configId) {
      showToast("请先选择部署配置", true);
      return;
    }
    const config = state.deploymentConfigs.find((item) => item.id === configId);
    if (!config) {
      showToast("部署配置不存在或已删除", true);
      return;
    }
    fillDeployFormByConfig(config);
    showToast(`已加载部署配置 #${configId}`);
  });

  byId("deleteDeployConfigBtn").addEventListener("click", async () => {
    const configId = Number(byId("deployConfigSelect").value || byId("deployConfigIdInput").value);
    if (!configId) {
      showToast("请先选择部署配置", true);
      return;
    }
    await deleteDeploymentConfig(configId);
  });

  byId("saveDeployConfigBtn").addEventListener("click", async () => {
    const configName = byId("deployConfigNameInput").value.trim();
    if (!configName) {
      showToast("保存配置时请填写部署配置名称", true);
      return;
    }
    const payload = getDeployPayloadFromForm();
    const errorText = validateDeployConfigPayload(payload);
    if (errorText) {
      showToast(errorText, true);
      return;
    }
    try {
      const config = await api("/api/deploy-configs", {
        method: "POST",
        body: {
          name: configName,
          app_id: payload.app_id,
          environment_id: payload.environment_id,
          mode: payload.mode,
          build_id: payload.build_id,
          image_ref: payload.image_ref,
          container_name: payload.container_name,
          ports: payload.ports,
          env_vars: payload.env_vars,
          compose_content: payload.compose_content,
          remote_dir: payload.remote_dir,
          timeout_seconds: payload.timeout_seconds,
        },
      });
      setSelectedDeployConfigId(config.id);
      await loadDeploymentConfigs();
      showToast(`部署配置已保存 #${config.id}`);
    } catch (error) {
      showToast(`保存部署配置失败: ${error.message}`, true);
    }
  });

  byId("updateDeployConfigBtn").addEventListener("click", async () => {
    const configId = Number(byId("deployConfigIdInput").value || byId("deployConfigSelect").value);
    if (!configId) {
      showToast("请先选择部署配置再更新", true);
      return;
    }
    const configName = byId("deployConfigNameInput").value.trim();
    if (!configName) {
      showToast("更新配置时请填写部署配置名称", true);
      return;
    }
    const payload = getDeployPayloadFromForm();
    const errorText = validateDeployConfigPayload(payload);
    if (errorText) {
      showToast(errorText, true);
      return;
    }
    try {
      const config = await api(`/api/deploy-configs/${configId}`, {
        method: "PUT",
        body: {
          name: configName,
          app_id: payload.app_id,
          environment_id: payload.environment_id,
          mode: payload.mode,
          build_id: payload.build_id,
          image_ref: payload.image_ref,
          container_name: payload.container_name,
          ports: payload.ports,
          env_vars: payload.env_vars,
          compose_content: payload.compose_content,
          remote_dir: payload.remote_dir,
          timeout_seconds: payload.timeout_seconds,
        },
      });
      setSelectedDeployConfigId(config.id);
      await loadDeploymentConfigs();
      showToast(`部署配置已更新 #${config.id}`);
    } catch (error) {
      showToast(`更新部署配置失败: ${error.message}`, true);
    }
  });

  byId("clearDeployConfigSelectionBtn").addEventListener("click", () => {
    setSelectedDeployConfigId(null);
    byId("deployConfigNameInput").value = "";
    showToast("已清空部署配置选择");
  });

  byId("watchDeployBtn").addEventListener("click", async () => {
    const deployId = Number(byId("selectedDeployIdInput").value);
    if (!deployId) {
      showToast("请输入 Deploy ID", true);
      return;
    }
    await watchDeployment(deployId);
  });

  byId("viewDeployDetailBtn").addEventListener("click", async () => {
    const deployId = Number(byId("selectedDeployIdInput").value);
    if (!deployId) {
      showToast("请输入 Deploy ID", true);
      return;
    }
    await viewDeploymentDetail(deployId);
  });

  byId("runLocalPrecheckBtn").addEventListener("click", async () => {
    renderPrecheckLoading("local", "正在执行本地预检查");
    setOutput("localPrecheckOut", "执行中...");
    try {
      const data = await api("/api/precheck/local");
      renderPrecheckVisual("local", data);
      setOutput("localPrecheckOut", formatPrecheckResult(data));
      showToast("本地预检查完成");
    } catch (error) {
      renderPrecheckVisual(
        "local",
        { ok: false, items: [{ name: "local_precheck", ok: false, detail: String(error.message || error) }] },
        "接口执行失败"
      );
      setOutput("localPrecheckOut", `执行失败: ${error.message}`);
      showToast("本地预检查失败", true);
    }
  });

  byId("runRemotePrecheckBtn").addEventListener("click", async () => {
    const envId = Number(byId("remoteEnvSelect").value);
    if (!envId) {
      showToast("请选择远程环境", true);
      return;
    }
    const envLabel = byId("remoteEnvSelect").selectedOptions?.[0]?.textContent || `#${envId}`;
    renderPrecheckLoading("remote", `正在检查环境 ${envLabel}`);
    setOutput("remotePrecheckOut", "执行中...");
    try {
      const data = await api(`/api/precheck/remote/${envId}`);
      renderPrecheckVisual("remote", data, `环境 ${envLabel}`);
      setOutput("remotePrecheckOut", formatPrecheckResult(data));
      showToast("远程预检查完成");
    } catch (error) {
      renderPrecheckVisual(
        "remote",
        { ok: false, items: [{ name: "remote_precheck", ok: false, detail: String(error.message || error) }] },
        `环境 ${envLabel}`
      );
      setOutput("remotePrecheckOut", `执行失败: ${error.message}`);
      showToast("远程预检查失败", true);
    }
  });

  byId("envTestBtn").addEventListener("click", async () => {
    const payload = {
      host: byId("envHostInput").value.trim(),
      port: Number(byId("envPortInput").value || "22"),
      username: byId("envUserInput").value.trim(),
      password: byId("envPasswordInput").value,
    };
    if (!payload.host || !payload.username || !payload.password) {
      showToast("请先填写 Host、用户名、密码", true);
      return;
    }

    setOutput("envTestOut", "连接测试中...");
    try {
      const data = await api("/api/environments/test-connection", { method: "POST", body: payload });
      setOutput("envTestOut", `ok=${data.ok}\ndetail=${data.detail}`);
      showToast(data.ok ? "SSH 连接成功" : "SSH 连接失败", !data.ok);
    } catch (error) {
      setOutput("envTestOut", `执行失败: ${error.message}`);
      showToast(`测试连接失败: ${error.message}`, true);
    }
  });
}

async function bootstrap() {
  bindNavigation();
  bindForms();
  bindActions();
  await loadAll();
}

window.addEventListener("beforeunload", () => {
  closeBuildWatch();
  closeDeployWatch();
  closeImageRepoDeployWatch();
});

window.addEventListener("DOMContentLoaded", () => {
  bootstrap().catch((error) => showToast(`初始化失败: ${error.message}`, true));
});
