const btn = document.getElementById("btn");
let n = Number(localStorage.getItem("count") || 0);
btn.textContent = n;
btn.onclick = () => { n++; btn.textContent = n; localStorage.setItem("count", n); };
document.getElementById("where").textContent = "Running from " + location.origin;
