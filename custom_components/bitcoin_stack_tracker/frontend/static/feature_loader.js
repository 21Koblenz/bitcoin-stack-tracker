"use strict";

(async () => {
  const fallback = "index.html?native=1&feature_fallback=1";
  try {
    const response = await fetch(`index.html?feature_base=${Date.now()}`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error(`index.html HTTP ${response.status}`);

    let html = await response.text();
    const injection = [
      '<script src="static/booking_value_math.js?v=0.21.0.16"><\/script>',
      '<script src="static/booking_tax_features.js?v=0.21.0.16"><\/script>',
    ].join("");

    if (!html.includes("</body>")) throw new Error("index.html has no </body>");
    html = html.replace("</body>", `${injection}</body>`);

    document.open();
    document.write(html);
    document.close();
  } catch (error) {
    console.error("Bitcoin Stack feature loader failed", error);
    // Fail safe: never leave the user with a blank panel.
    window.location.replace(fallback);
  }
})();
