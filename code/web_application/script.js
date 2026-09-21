// ===== DATA-260 HW2 Part 1/2: Entity list + form wired to FastAPI backend =====
//
// Same-origin API since FastAPI serves this file directly:
//   GET    /api/incidents?q=<search>   -> list (optionally filtered)
//   POST   /api/incidents              -> add a new incident
//   PUT    /api/incidents/1            -> update record ID 1 (domain demo)
//   DELETE /api/incidents/highest      -> delete the highest-ID record
const API_BASE = "/api/incidents";

const stateLoading = document.getElementById("stateLoading");
const stateEmpty = document.getElementById("stateEmpty");
const stateError = document.getElementById("stateError");
const table = document.getElementById("incidentTable");
const tableBody = document.getElementById("incidentTableBody");
const resultCount = document.getElementById("resultCount");
const searchInput = document.getElementById("searchInput");
const actionStatus = document.getElementById("actionStatus");

const CATEGORY_CLASS = {
  "Delay": "delay",
  "Breakdown": "breakdown",
  "Accident": "accident",
  "Service Change": "service-change",
};


function showState(state) {
  [stateLoading, stateEmpty, stateError, table].forEach((el) => {
    if (el === table) {
      el.style.display = "none";
    } else {
      el.classList.remove("is-visible");
    }
  });
  if (state === "loading") stateLoading.classList.add("is-visible");
  if (state === "empty") stateEmpty.classList.add("is-visible");
  if (state === "error") stateError.classList.add("is-visible");
  if (state === "table") table.style.display = "table";
}

function renderRows(incidents) {
  tableBody.innerHTML = "";
  incidents.forEach((incident) => {
    const tr = document.createElement("tr");
    const catClass = CATEGORY_CLASS[incident.category] || "delay";
    tr.innerHTML = `
      <td class="id-cell" data-label="ID">#${incident.id}</td>
      <td data-label="Route / Title">${escapeHtml(incident.routeId)}</td>
      <td data-label="Location">${escapeHtml(incident.location)}</td>
      <td data-label="Category"><span class="tag-pill ${catClass}">${escapeHtml(incident.category)}</span></td>
    `;
    tableBody.appendChild(tr);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}


async function loadIncidents(query = "") {
  showState("loading");
  resultCount.textContent = "";

  const url = query ? `${API_BASE}?q=${encodeURIComponent(query)}` : API_BASE;

  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Server responded ${response.status}`);
    const incidents = await response.json();

    if (incidents.length === 0) {
      showState("empty");
      resultCount.textContent = "0 results";
      return;
    }

    renderRows(incidents);
    showState("table");
    resultCount.textContent = `${incidents.length} result${incidents.length === 1 ? "" : "s"}`;
  } catch (err) {
    console.error("Failed to load incidents:", err);
    showState("error");
  }
}

let searchDebounce;
searchInput.addEventListener("input", (event) => {
  clearTimeout(searchDebounce);
  const value = event.target.value.trim();
  searchDebounce = setTimeout(() => loadIncidents(value), 250);
});

document.getElementById("retryBtn").addEventListener("click", () => {
  loadIncidents(searchInput.value.trim());
});


document.getElementById("updateFirstBtn").addEventListener("click", async () => {
  actionStatus.textContent = "Updating record #1...";
  actionStatus.className = "inline-status";
  try {
    const response = await fetch(`${API_BASE}/1`, { method: "PUT" });
    if (!response.ok) throw new Error(`Server responded ${response.status}`);
    // Literal redirect to the home view showing the updated list, per spec.
    window.location.href = "/";
  } catch (err) {
    console.error("Update failed:", err);
    actionStatus.textContent = "Failed to update record #1.";
    actionStatus.className = "inline-status fail";
  }
});

// ---- Demo action: delete the highest-ID record ----
document.getElementById("deleteHighestBtn").addEventListener("click", async () => {
  actionStatus.textContent = "Deleting highest-ID record...";
  actionStatus.className = "inline-status";
  try {
    const response = await fetch(`${API_BASE}/highest`, { method: "DELETE" });
    if (!response.ok) throw new Error(`Server responded ${response.status}`);
    window.location.href = "/";
  } catch (err) {
    console.error("Delete failed:", err);
    actionStatus.textContent = "Failed to delete highest-ID record.";
    actionStatus.className = "inline-status fail";
  }
});

// ===== Part II: JavaScript (retained from HW1) =====

// 5. Closure to track how many times the form has been successfully submitted
const createSubmissionCounter = () => {
  let count = 0;
  return () => {
    count += 1;
    return count;
  };
};
const trackSubmission = createSubmissionCounter();

// 1. Arrow function validation
const validateForm = (data) => {
  // a) description must be more than 25 characters
  if (!data.description || data.description.length <= 25) {
    alert("Please enter a description with more than 25 characters.");
    return false;
  }

  // b) terms and conditions checkbox must be checked
  if (!data.agreeToTerms) {
    alert("You must agree to the terms and conditions before submitting.");
    return false;
  }

  return true;
};

document.getElementById("incidentForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const form = event.target;
  const formData = {
    routeId: form.routeId.value,
    location: form.location.value,
    reporterEmail: form.reporterEmail.value,
    description: form.description.value,
    category: form.category.value,
    agreeToTerms: form.agreeToTerms.checked,
  };

  if (!validateForm(formData)) {
    return;
  }

  // 2. Convert form data into a JSON string and log it
  const jsonString = JSON.stringify(formData);
  console.log("Form data as JSON string:", jsonString);

  // Parse it back into an object to work with below
  const parsedData = JSON.parse(jsonString);

  // 3. Object destructuring to extract primary field and email, then log them
  const { routeId, reporterEmail } = parsedData;
  console.log("Primary field (routeId):", routeId);
  console.log("Email field (reporterEmail):", reporterEmail);

  // 4. Spread operator to add submissionDate to the parsed object
  const updatedData = {
    ...parsedData,
    submissionDate: new Date().toISOString(),
  };
  console.log("Updated parsed object with submissionDate:", updatedData);

  // ---- Send to backend (Part 2: add record), then redirect to home ----
  try {
    const response = await fetch(API_BASE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updatedData),
    });
    if (!response.ok) throw new Error(`Server responded ${response.status}`);

    // 5. Log the submission count using the closure
    const submissionCount = trackSubmission();
    console.log("Total successful submissions this session:", submissionCount);

    window.location.href = "/";
  } catch (err) {
    console.error("Failed to submit incident:", err);
    alert("Could not submit the incident report. Please try again.");
  }
});

// ---- Initial load ----
loadIncidents();