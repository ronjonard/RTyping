const menuButton = document.getElementById("menuButton");
const dropdownMenu = document.getElementById("dropdownMenu");

if (menuButton && dropdownMenu) {
    menuButton.addEventListener("click", () => {
        dropdownMenu.classList.toggle("show");
    });

    document.addEventListener("click", (event) => {
        if (
            !menuButton.contains(event.target) &&
            !dropdownMenu.contains(event.target)
        ) {
            dropdownMenu.classList.remove("show");
        }
    });
}

const beginButton = document.getElementById("beginButton");

if (beginButton) {
    beginButton.addEventListener("click", () => {
        const difficulty = document.getElementById("difficulty").value;
        const duration = document.getElementById("duration").value;

        const params = new URLSearchParams({
            difficulty: difficulty,
            duration: duration
        });

        window.location.href = "/typing?" + params.toString();
    });
}