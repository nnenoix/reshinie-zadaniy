// Вкладки по образцу WAI-ARIA для /app и /login. В порядке Tab — только выбранная вкладка
// (roving tabindex), стрелки ←/→, Home и End переходят между вкладками. Саму вкладку
// переключает обработчик клика страницы (app.js, login.js): здесь только клавиатура и tabindex.

const STEP = { ArrowRight: 1, ArrowLeft: -1 };

function wire(list) {
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  const sync = () => tabs.forEach((tab) => { tab.tabIndex = tab.getAttribute("aria-selected") === "true" ? 0 : -1; });
  new MutationObserver(sync).observe(list, { subtree: true, attributeFilter: ["aria-selected"] });
  sync();

  list.addEventListener("keydown", (event) => {
    const at = tabs.indexOf(document.activeElement);
    if (at < 0) return;
    const to = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
      : event.key in STEP ? (at + STEP[event.key] + tabs.length) % tabs.length : null;
    if (to === null) return;
    event.preventDefault();
    tabs[to].click();
    tabs[to].focus(); // login.js после клика ставит фокус в поле формы — возвращаем его на вкладку
  });
}

document.querySelectorAll('[role="tablist"]').forEach(wire);
