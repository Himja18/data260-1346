// ===== Part II: JavaScript =====

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

document.getElementById("incidentForm").addEventListener("submit", (event) => {
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

  // 5. Log the submission count using the closure
  const submissionCount = trackSubmission();
  console.log("Total successful submissions this session:", submissionCount);

  alert("Incident reported successfully!");
  form.reset();
  form.routeId.focus();
});