const dssActionHandlers = new Map();

window.dssAction = (action, ...args) =>
  `data-dss-action="${action}" data-dss-event="click" data-dss-args="${encodeURIComponent(JSON.stringify(args))}"`;

window.dssChangeAction = (action, ...args) =>
  `data-dss-action="${action}" data-dss-event="change" data-dss-args="${encodeURIComponent(JSON.stringify(args))}"`;

window.registerDssAction = (action, handler) => {
  dssActionHandlers.set(action, handler);
};

function dispatchDssAction(event) {
  const element = event.target.closest("[data-dss-action]");
  if (!element || (element.dataset.dssEvent || "click") !== event.type) return;

  const handler = dssActionHandlers.get(element.dataset.dssAction);
  if (!handler) return;

  try {
    const args = JSON.parse(decodeURIComponent(element.dataset.dssArgs || "%5B%5D"));
    Promise.resolve(handler(...args, element)).catch(error => {
      console.error("DSS action failed:", error);
    });
  } catch (error) {
    console.error("Unable to process DSS action:", error);
  }
}

document.addEventListener("click", dispatchDssAction);
document.addEventListener("change", dispatchDssAction);
