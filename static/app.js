const inspectForm = document.querySelector("#inspect-form");
const convertForm = document.querySelector("#convert-form");
const fileInput = document.querySelector("#invoice-file");
const dropzone = document.querySelector("#dropzone");
const fileLabel = document.querySelector("#file-label");
const uploadPanel = document.querySelector("#upload-panel");
const reviewPanel = document.querySelector("#review-panel");
const resultPanel = document.querySelector("#result-panel");
const statusLine = document.querySelector("#status");
const warningsBox = document.querySelector("#warnings");
let selectedFile = null;
let outputUrl = null;

function setStatus(message, isError = false) {
    statusLine.textContent = message;
    statusLine.classList.toggle("is-error", isError);
}

function setBusy(button, busy, busyText, idleText) {
    button.disabled = busy;
    button.innerHTML = busy ? `${busyText} <span aria-hidden="true">…</span>` : idleText;
}

async function responseError(response) {
    try {
        const payload = await response.json();
        return payload.error || "Something went wrong. Please try again.";
    } catch {
        return response.status === 413
            ? "This PDF is larger than the 20 MB upload limit."
            : "Something went wrong. Please try again.";
    }
}

function selectFile(file) {
    if (!file) return;
    selectedFile = file;
    fileLabel.textContent = file.name;
    setStatus("");
}

fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));
for (const eventName of ["dragenter", "dragover"]) {
    dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
    });
}
for (const eventName of ["dragleave", "drop"]) {
    dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.remove("is-dragging");
    });
}
dropzone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));

inspectForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedFile) {
        setStatus("Choose a PDF invoice first.", true);
        return;
    }
    const button = document.querySelector("#inspect-button");
    setBusy(button, true, "Reading invoice", "Read invoice <span aria-hidden=\"true\">→</span>");
    setStatus("");
    const data = new FormData();
    data.append("invoice", selectedFile);
    try {
        const response = await fetch("/inspect", { method: "POST", body: data });
        if (!response.ok) throw new Error(await responseError(response));
        const fields = await response.json();
        document.querySelector("#issue-date").value = fields.issue_date;
        document.querySelector("#usd-total").value = fields.usd_total;
        warningsBox.replaceChildren(...fields.warnings.map((warning) => {
            const paragraph = document.createElement("p");
            paragraph.textContent = warning;
            return paragraph;
        }));
        warningsBox.classList.toggle("is-hidden", fields.warnings.length === 0);
        uploadPanel.classList.add("is-hidden");
        reviewPanel.classList.remove("is-hidden");
        document.querySelector("#step-upload").classList.replace("is-current", "is-done");
        document.querySelector("#step-review").classList.add("is-current");
        setStatus("");
        reviewPanel.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (error) {
        setStatus(error.message, true);
    } finally {
        setBusy(button, false, "Reading invoice", "Read invoice <span aria-hidden=\"true\">→</span>");
    }
});

convertForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedFile || !convertForm.reportValidity()) return;
    const button = document.querySelector("#convert-button");
    setBusy(button, true, "Checking official rate", "Confirm &amp; convert <span aria-hidden=\"true\">→</span>");
    setStatus("Looking up the official rate for your invoice date…");
    const data = new FormData();
    data.append("invoice", selectedFile);
    data.append("issue_date", document.querySelector("#issue-date").value);
    data.append("usd_total", document.querySelector("#usd-total").value);
    try {
        const response = await fetch("/convert", { method: "POST", body: data });
        if (!response.ok) throw new Error(await responseError(response));
        const pdf = await response.blob();
        if (outputUrl) URL.revokeObjectURL(outputUrl);
        outputUrl = URL.createObjectURL(pdf);
        const download = document.querySelector("#download-link");
        download.href = outputUrl;
        download.download = `${selectedFile.name.replace(/\.pdf$/i, "")} EUR.pdf`;
        selectedFile = null;
        fileInput.value = "";
        const sourceDate = response.headers.get("X-Rate-Date");
        const sourceRate = response.headers.get("X-USD-Per-EUR");
        const usdTotal = Number(response.headers.get("X-USD-Total"));
        const eurTotal = Number(response.headers.get("X-EUR-Total"));
        document.querySelector("#result-total").textContent = `€${eurTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        document.querySelector("#result-usd").textContent = `$${usdTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        document.querySelector("#result-rate").textContent = `1 EUR = ${sourceRate} USD`;
        document.querySelector("#result-date").textContent = sourceDate;
        reviewPanel.classList.add("is-hidden");
        resultPanel.classList.remove("is-hidden");
        document.querySelector("#step-review").classList.replace("is-current", "is-done");
        document.querySelector("#step-download").classList.add("is-current");
        setStatus("");
        resultPanel.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (error) {
        setStatus(error.message, true);
    } finally {
        setBusy(button, false, "Checking official rate", "Confirm &amp; convert <span aria-hidden=\"true\">→</span>");
    }
});

function resetFlow() {
    if (outputUrl) URL.revokeObjectURL(outputUrl);
    outputUrl = null;
    selectedFile = null;
    fileInput.value = "";
    fileLabel.innerHTML = 'Drop a PDF here or <u>browse files</u>';
    convertForm.reset();
    warningsBox.classList.add("is-hidden");
    resultPanel.classList.add("is-hidden");
    reviewPanel.classList.add("is-hidden");
    uploadPanel.classList.remove("is-hidden");
    document.querySelector("#step-upload").className = "step is-current";
    document.querySelector("#step-review").className = "step";
    document.querySelector("#step-download").className = "step";
    setStatus("");
}

document.querySelector("#change-file").addEventListener("click", resetFlow);
document.querySelector("#new-invoice").addEventListener("click", resetFlow);
