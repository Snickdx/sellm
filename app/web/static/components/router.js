/**
 * History-API router for the unified student shell.
 */
(function (global) {
  const VIEWS = {
    landing: "view-landing",
    req: "view-req",
    exit: "view-exit",
    policy: "view-policy",
  };

  let booted = false;
  let user = null;
  let currentView = null;

  function $(id) {
    return document.getElementById(id);
  }

  function pathOf(pathname) {
    const p = (pathname || "/").replace(/\/+$/, "") || "/";
    return p;
  }

  function matchRoute(pathname) {
    const p = pathOf(pathname);
    if (p === "/" || p === "/login" || p === "/claim") return { view: "landing", teamId: null };
    if (p === "/req") return { view: "req", teamId: null };
    if (p === "/exit") return { view: "exit", teamId: null };
    if (p === "/policy") return { view: "policy", teamId: null };
    const teamExit = p.match(/^\/teams\/([^/]+)\/exit$/);
    if (teamExit) return { view: "exit", teamId: teamExit[1] };
    return { view: "landing", teamId: null };
  }

  function setNavCurrent(view) {
    document.querySelectorAll("[data-nav]").forEach((el) => {
      const isCurrent = el.getAttribute("data-nav") === view;
      el.classList.toggle("active", isCurrent);
      if (isCurrent) el.setAttribute("aria-current", "page");
      else el.removeAttribute("aria-current");
    });
  }

  function blurIfInside(el) {
    const focused = document.activeElement;
    if (focused && el && el.contains(focused) && typeof focused.blur === "function") {
      focused.blur();
    }
  }

  function showOnly(viewKey) {
    Object.keys(VIEWS).forEach((key) => {
      const el = $(VIEWS[key]);
      if (!el) return;
      const on = key === viewKey;
      if (!on) blurIfInside(el);
      el.hidden = !on;
      el.setAttribute("aria-hidden", on ? "false" : "true");
      // Prefer inert on hidden panes so focused descendants cannot remain interactive.
      if ("inert" in el) el.inert = !on;
    });
    currentView = viewKey;
    if (global.SellmChat && typeof global.SellmChat.closeMobileNavs === "function") {
      global.SellmChat.closeMobileNavs();
    }
  }

  function showShell(show) {
    const shell = $("appShell");
    const landing = $(VIEWS.landing);
    if (shell) {
      shell.hidden = !show;
      shell.setAttribute("aria-hidden", show ? "false" : "true");
    }
    if (!show && landing) {
      landing.hidden = false;
      landing.setAttribute("aria-hidden", "false");
    }
  }

  function updateAdminLinks() {
    const isAdmin = Boolean(user && (user.is_admin || user.role === "admin"));
    ["adminLink", "adminLinkMobile"].forEach((id) => {
      const link = $(id);
      if (!link) return;
      if (isAdmin) {
        link.hidden = false;
        link.style.display = id === "adminLinkMobile" ? "inline-flex" : "block";
      } else {
        link.hidden = true;
        link.style.display = "none";
      }
    });
  }

  async function refreshUser() {
    const token = global.SellmApi.getToken();
    if (!token) {
      user = null;
      updateAdminLinks();
      return null;
    }
    try {
      user = await global.SellmApi.me();
      updateAdminLinks();
      return user;
    } catch (_) {
      global.SellmApi.setToken(null);
      user = null;
      updateAdminLinks();
      return null;
    }
  }

  async function applyRoute(pathname, { replace } = {}) {
    const route = matchRoute(pathname);
    const authed = Boolean(user);

    if (!authed) {
      showShell(false);
      showOnly("landing");
      setNavCurrent("landing");
      if (global.SellmClaim) global.SellmClaim.mount();
      const target = pathOf(pathname);
      if (target !== "/" && target !== "/login" && target !== "/claim") {
        history.replaceState({}, "", "/");
      } else if (replace) {
        history.replaceState({}, "", target === "/claim" || target === "/login" ? target : "/");
      }
      return;
    }

    // Logged in: landing paths go to exit.
    if (route.view === "landing") {
      const dest = "/exit";
      if (replace || pathOf(pathname) !== dest) {
        history.replaceState({}, "", dest);
      }
      return applyRoute(dest, { replace: true });
    }

    showShell(true);
    showOnly(route.view);
    setNavCurrent(route.view === "policy" ? "exit" : route.view);

    if (route.view === "req" && global.SellmChat && typeof global.SellmChat.activate === "function") {
      await global.SellmChat.activate();
    }
    if (route.view === "exit" && global.SellmExit) {
      await global.SellmExit.mount({ teamId: route.teamId });
    }
    if (route.view === "policy" && global.SellmExit) {
      await global.SellmExit.mountPolicy();
    }
  }

  function navigate(pathname, { replace } = {}) {
    const next = pathOf(pathname);
    if (replace) history.replaceState({}, "", next);
    else if (pathOf(location.pathname) !== next) history.pushState({}, "", next);
    return applyRoute(next, { replace });
  }

  function interceptClicks(event) {
    const a = event.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
    const href = a.getAttribute("href");
    if (!href || href.startsWith("http") || href.startsWith("mailto:") || href.startsWith("#")) return;
    if (href.startsWith("/admin") || href.startsWith("/api") || href.startsWith("/static")) return;
    const url = new URL(href, location.origin);
    if (url.origin !== location.origin) return;
    const route = matchRoute(url.pathname);
    // Only intercept shell routes
    if (!["landing", "req", "exit", "policy"].includes(route.view) && !url.pathname.startsWith("/teams/")) {
      return;
    }
    event.preventDefault();
    navigate(url.pathname + url.search);
  }

  async function onLoggedIn(token) {
    global.SellmApi.setToken(token);
    if (global.SellmChat && typeof global.SellmChat.syncToken === "function") {
      global.SellmChat.syncToken();
    }
    await refreshUser();
    await navigate("/exit", { replace: true });
  }

  async function requireAuth() {
    user = null;
    updateAdminLinks();
    showShell(false);
    showOnly("landing");
    if (global.SellmClaim) global.SellmClaim.mount();
    if (pathOf(location.pathname) !== "/") {
      history.replaceState({}, "", "/");
    }
  }

  async function boot() {
    if (booted) return;
    booted = true;
    document.body.addEventListener("click", interceptClicks);
    window.addEventListener("popstate", () => {
      void applyRoute(location.pathname);
    });
    await refreshUser();
    await applyRoute(location.pathname, { replace: true });
  }

  global.SellmRouter = {
    boot,
    navigate,
    onLoggedIn,
    requireAuth,
    getUser: () => user,
    refreshUser,
    currentView: () => currentView,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => void boot());
  } else {
    void boot();
  }
})(window);
