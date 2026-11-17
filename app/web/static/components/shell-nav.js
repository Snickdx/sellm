/** Mobile side-nav toggle for student shell pages. */
(function () {
  function $(id) {
    return document.getElementById(id);
  }
  const shell = $("appShell");
  const pane = $("appNavPane");
  const backdrop = $("sideNavBackdrop");
  function openNav() {
    shell?.classList.add("nav-open");
    if (backdrop) {
      backdrop.classList.add("visible");
      backdrop.setAttribute("aria-hidden", "false");
    }
  }
  function closeNav() {
    shell?.classList.remove("nav-open");
    if (backdrop) {
      backdrop.classList.remove("visible");
      backdrop.setAttribute("aria-hidden", "true");
    }
  }
  document.querySelectorAll(".side-nav-toggle").forEach((btn) => {
    btn.addEventListener("click", openNav);
  });
  $("appNavClose")?.addEventListener("click", closeNav);
  backdrop?.addEventListener("click", closeNav);
})();
