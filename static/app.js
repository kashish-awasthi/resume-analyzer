const $ = (id) => document.getElementById(id);

const form = $("form");
const fileInput = $("file");
const drop = $("drop");
const dropText = $("drop-text");
let lastResumeText = "";
let lastJob = "";

// ---------- helpers ----------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "style") node.setAttribute("style", v);
    else node[k] = v;
  }
  for (const c of children) node.append(c);
  return node;
}

function chips(container, items, emptyText) {
  container.replaceChildren();
  if (!items || items.length === 0) {
    container.append(el("span", { class: "none" }, emptyText));
    return;
  }
  for (const item of items) container.append(el("span", { class: "chip" }, item));
}

function showError(target, message) {
  target.textContent = message;
  target.hidden = !message;
}

async function postForm(url, formData) {
  const res = await fetch(url, { method: "POST", body: formData });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

function scoreColor(pct) {
  if (pct >= 85) return "var(--ok)";
  if (pct >= 55) return "var(--warn)";
  return "var(--bad)";
}

// ---------- file picking ----------

function setFile(file) {
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  drop.classList.add("has-file");
  dropText.replaceChildren(el("strong", {}, file.name), el("br"), el("small", {}, "Click to choose a different file"));
}

fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); })
);
["dragleave", "drop"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); })
);
drop.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

// ---------- sample ----------

$("sample").addEventListener("click", async () => {
  const res = await fetch("/api/sample");
  const sample = await res.json();
  fileInput.value = "";
  drop.classList.remove("has-file");
  dropText.replaceChildren(el("strong", {}, "Choose a file"), " or drag it here", el("br"), el("small", {}, "PDF, DOCX or TXT, up to 5 MB"));
  $("resume_text").value = sample.resume_text;
  $("job_description").value = sample.job_description;
  document.querySelector(".paste").open = true;
  form.requestSubmit();
});

// ---------- analyze ----------

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  showError($("error"), "");
  const btn = $("submit");
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  try {
    const fd = new FormData(form);
    if (!fileInput.files.length) fd.delete("file");
    const result = await postForm("/api/analyze", fd);
    lastResumeText = result.resume_text;
    lastJob = $("job_description").value;
    render(result);
  } catch (err) {
    showError($("error"), err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze resume";
  }
});

function render(r) {
  $("results").hidden = false;

  // score ring
  const ring = $("ring");
  ring.style.setProperty("--pct", r.score);
  ring.style.setProperty("--color", scoreColor(r.score));
  $("score").textContent = r.score;
  $("grade").textContent = r.grade;
  $("score-caption").textContent = r.job_match
    ? "Includes how well you match this job."
    : "Add a job description to see your match.";

  // job match
  const mc = $("match-card");
  if (r.job_match) {
    mc.hidden = false;
    $("match-pct").textContent = `${r.job_match.match_percent}%`;
    chips($("matched"), r.job_match.matched_skills, "None of the listed skills found");
    chips($("missing"), r.job_match.missing_skills, "Nothing missing");
    chips($("missing-kw"), r.job_match.missing_keywords, "All covered");
  } else {
    mc.hidden = true;
  }

  // breakdown
  const bd = $("breakdown");
  bd.replaceChildren();
  for (const part of r.breakdown) {
    const pct = Math.round((100 * part.score) / part.max);
    const notes = el("ul", { class: "bar-notes" });
    for (const n of part.notes) notes.append(el("li", {}, n));
    bd.append(
      el("div", { class: "bar-row" },
        el("div", { class: "bar-label" }, el("span", {}, part.name), el("span", {}, `${part.score} / ${part.max}`)),
        el("div", { class: "bar" }, el("div", { style: `width:${pct}%;background:${scoreColor(pct)}` })),
        notes,
      )
    );
  }

  // suggestions
  const sg = $("suggestions");
  sg.replaceChildren();
  if (r.suggestions.length === 0) sg.append(el("li", {}, "Nothing major. Nice work!"));
  for (const s of r.suggestions) sg.append(el("li", {}, s));

  // skills
  const sk = $("skills");
  sk.replaceChildren();
  const groups = Object.entries(r.skills_found);
  if (groups.length === 0) sk.append(el("p", { class: "muted" }, "No known skills found."));
  for (const [cat, list] of groups) {
    const c = el("div", { class: "chips" });
    chips(c, list, "");
    sk.append(el("div", { class: "skill-group" }, el("h3", {}, cat), c));
  }

  // checklist
  const cl = $("checklist");
  cl.replaceChildren();
  const checks = [
    ...Object.entries(r.contact).map(([k, v]) => [k === "linkedin" ? "LinkedIn" : k === "github" ? "GitHub" : k[0].toUpperCase() + k.slice(1), !!v]),
    ...Object.entries(r.sections).map(([k, v]) => [`${k} section`, v]),
  ];
  for (const [label, ok] of checks) cl.append(el("li", { class: ok ? "yes" : "no" }, label));

  // stats
  const st = $("stats");
  st.replaceChildren();
  const labels = {
    word_count: "Words",
    bullet_points: "Bullet points",
    action_verb_bullets: "Start with action verb",
    quantified_bullets: "Include a number",
    skills_count: "Skills detected",
  };
  for (const [k, v] of Object.entries(r.stats)) st.append(el("dt", {}, labels[k] || k), el("dd", {}, String(v)));

  // reset AI section
  $("ai-result").hidden = true;
  showError($("ai-error"), "");

  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- AI review ----------

$("ai-btn").addEventListener("click", async () => {
  const btn = $("ai-btn");
  btn.disabled = true;
  btn.textContent = "Reviewing... (up to a minute)";
  showError($("ai-error"), "");
  try {
    const fd = new FormData();
    fd.append("resume_text", lastResumeText);
    fd.append("job_description", lastJob);
    renderAI(await postForm("/api/ai-review", fd));
  } catch (err) {
    showError($("ai-error"), err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Get AI review";
  }
});

function list(items) {
  const ul = el("ul");
  for (const i of items) ul.append(el("li", {}, i));
  return ul;
}

function renderAI(ai) {
  const out = $("ai-result");
  out.replaceChildren(el("p", {}, ai.overall_impression));
  if (ai.strengths.length) out.append(el("h3", {}, "Strengths"), list(ai.strengths));
  if (ai.improvements.length) {
    out.append(el("h3", {}, "What to improve"));
    const ul = el("ul");
    for (const i of ai.improvements) ul.append(el("li", {}, el("strong", {}, i.issue), " " + i.fix));
    out.append(ul);
  }
  if (ai.rewritten_bullets.length) {
    out.append(el("h3", {}, "Rewritten bullet points"));
    for (const b of ai.rewritten_bullets) {
      out.append(el("div", { class: "rewrite" }, el("p", { class: "before" }, b.original), el("p", { class: "after" }, b.improved)));
    }
  }
  if (ai.missing_for_job.length) out.append(el("h3", {}, "Missing for this job"), list(ai.missing_for_job));
  out.hidden = false;
}

// ---------- startup ----------

fetch("/api/health")
  .then((r) => r.json())
  .then((h) => {
    if (!h.ai_available) {
      $("ai-btn").hidden = true;
      $("ai-off").hidden = false;
    }
  })
  .catch(() => {});
