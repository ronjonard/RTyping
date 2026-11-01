
document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector(".typing-page");
    const testScreen = document.getElementById("test-screen");
    const resultScreen = document.getElementById("result-screen");
    const typingText = document.getElementById("typing-text");
    const typingInput = document.getElementById("typing-input");
    const timerDisplay = document.getElementById("timer");

    const restartButton = document.getElementById("restart-button");
    const exitButton = document.getElementById("exit-button");
    const tryAgainButton = document.getElementById("try-again-button");

    const finalWpm = document.getElementById("final-wpm");
    const finalAccuracy = document.getElementById("final-accuracy");
    const finalTime = document.getElementById("final-time");
    const finalErrors = document.getElementById("final-errors");
    const saveStatus = document.getElementById("save-status");

    const paragraphCard = document.querySelector(".paragraph-card");

    const selectedParagraph = typingText.textContent.trim();
    const duration = Number.parseInt(page.dataset.duration, 10) || 60;
    const paragraphId = Number.parseInt(page.dataset.paragraphId, 10);
    const isMobile = window.matchMedia("(max-width: 600px)").matches;

    let remaining = duration;
    let timerId = null;
    let started = false;
    let finished = false;
    let startedAt = null;
    let resultSaved = false;

    function formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;

        return String(mins).padStart(2, "0") + ":" +
            String(secs).padStart(2, "0");
    }

    /* ===== Focus Typing Input ===== */

    function focusTypingInput() {
        if (finished) return;

        typingInput.focus({ preventScroll: true });
    }

    /* ===== Scroll to Current Character ===== */

    function scrollToCurrentCharacter() {
        const current = typingText.querySelector(".current");

        if (!current) return;

        const cardRect = paragraphCard.getBoundingClientRect();
        const currentRect = current.getBoundingClientRect();

        const bottomLimit = isMobile
            ? cardRect.bottom - 30
            : cardRect.bottom - (cardRect.height / 3);

        const topLimit = cardRect.top + 20;

        if (currentRect.bottom > bottomLimit) {
            const scrollAmount = currentRect.bottom - bottomLimit;
            paragraphCard.scrollTop += scrollAmount;
        } else if (currentRect.top < topLimit) {
            const scrollAmount = topLimit - currentRect.top;
            paragraphCard.scrollTop -= scrollAmount;
        }
    }

    /* ===== Display Paragraph ===== */

    function renderParagraph() {
        const typed = typingInput.value;

        typingText.replaceChildren();

        for (let i = 0; i < selectedParagraph.length; i++) {
            const span = document.createElement("span");

            span.textContent = selectedParagraph[i];

            if (i < typed.length) {
                if (typed[i] === selectedParagraph[i]) {
                    span.classList.add("correct");
                } else {
                    span.classList.add("incorrect");
                }
            } else if (i === typed.length && !finished) {
                span.classList.add("current");
            }

            typingText.appendChild(span);
        }

        scrollToCurrentCharacter();
    }

    /* ===== Calculate Results ===== */

    function calculateStats() {
        const typed = typingInput.value;

        let correctCharacters = 0;
        let totalErrors = 0;

        for (let i = 0; i < typed.length; i++) {
            if (
                i < selectedParagraph.length &&
                typed[i] === selectedParagraph[i]
            ) {
                correctCharacters++;
            } else {
                totalErrors++;
            }
        }

        const elapsed = startedAt
            ? Math.max(0, (Date.now() - startedAt) / 1000)
            : 0;

        const minutes = elapsed / 60;

        const wpm = minutes > 0
            ? Math.round((correctCharacters / 5) / minutes)
            : 0;

        const accuracy = typed.length > 0
            ? Math.round((correctCharacters / typed.length) * 100)
            : 100;

        return {
            wpm,
            accuracy,
            elapsed,
            totalErrors
        };
    }

    /* ===== Update Score Circle Fill ===== */

    function updateScoreCircle(element, percentage) {
        const circle = element.closest(".score-circle");

        if (!circle) return;

        const progress = Math.max(
            0,
            Math.min(100, percentage)
        );

        circle.style.setProperty(
            "--progress",
            progress + "%"
        );
    }

    function updateScoreCircles(stats) {
        // 120 WPM or higher = full circle
        const wpmProgress = (stats.wpm / 120) * 100;

        // 100% accuracy = full circle
        const accuracyProgress = stats.accuracy;

        updateScoreCircle(finalWpm, wpmProgress);
        updateScoreCircle(finalAccuracy, accuracyProgress);
    }

    /* ===== Start Timer ===== */

    function startTimer() {
        if (started || finished) return;

        started = true;
        startedAt = Date.now();

        timerId = setInterval(() => {
            remaining--;

            timerDisplay.textContent = formatTime(remaining);

            if (remaining <= 0) {
                finishTest();
            }
        }, 1000);
    }

    /* ===== Save Results ===== */

    async function saveResult(stats) {
        if (resultSaved) return;

        resultSaved = true;
        saveStatus.textContent = "Saving your results...";

        try {
            const response = await fetch("/save-result", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    wpm: stats.wpm,
                    accuracy: stats.accuracy,
                    duration_seconds: duration,
                    paragraph_id: paragraphId
                })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                saveStatus.textContent = data.message;
            } else {
                saveStatus.textContent =
                    data.message || "Unable to save your results.";
            }

        } catch (error) {
            console.error("Error saving results:", error);

            saveStatus.textContent =
                "Unable to connect to the server.";
        }
    }

    /* ===== Finish Test ===== */

    function finishTest() {
        if (finished) return;

        finished = true;

        clearInterval(timerId);

        typingInput.disabled = true;

        const stats = calculateStats();

        // Display final scores
        finalWpm.textContent = stats.wpm;
        finalAccuracy.textContent = stats.accuracy + "%";

        // Update circular progress
        updateScoreCircles(stats);

        finalTime.textContent = formatTime(
            Math.min(duration, Math.round(stats.elapsed))
        );

        finalErrors.textContent = stats.totalErrors;

        testScreen.hidden = true;
        resultScreen.hidden = false;

        // Save results
        saveResult(stats);
    }

    /* ===== Restart Test ===== */

    function resetTest() {
        window.location.reload();
    }

    /* ===== Event Listeners ===== */

    paragraphCard.addEventListener("click", () => {
        focusTypingInput();
    });

    typingInput.addEventListener("input", () => {
        if (finished) return;

        if (typingInput.value.length > 0) {
            startTimer();
        }

        renderParagraph();

        if (typingInput.value.length >= selectedParagraph.length) {
            finishTest();
        }
    });

    restartButton.addEventListener("click", resetTest);
    tryAgainButton.addEventListener("click", resetTest);

    exitButton.addEventListener("click", () => {
        clearInterval(timerId);
        window.location.href = "/";
    });

    /* ===== Initial Setup ===== */

    renderParagraph();

    timerDisplay.textContent = formatTime(duration);

    // Do not automatically open the mobile keyboard
    if (!isMobile) {
        focusTypingInput();
    }
});
