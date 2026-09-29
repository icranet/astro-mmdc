// Google Analytics consent defaults, loaded ahead of Material's gtag
// integration (extra.analytics in mkdocs.yml). Same rules as mmdc.am's ga.js:
// analytics cookies on by default, off in the EEA, the UK and Switzerland,
// no ads storage anywhere. The docs have no consent banner, so those regions
// stay cookieless.
(function () {
  // EU27, Iceland, Liechtenstein, Norway, the UK and Switzerland, plus the
  // EU's outermost regions that have their own ISO codes.
  var CONSENT_REGIONS = [
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "IS", "LI", "NO", "GB", "CH", "GF", "GP", "MQ", "YT",
    "RE", "MF",
  ];

  window.dataLayer = window.dataLayer || [];
  function gtag() {
    window.dataLayer.push(arguments);
  }

  var noAds = {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
  };
  gtag("consent", "default", Object.assign({ analytics_storage: "granted" }, noAds));
  gtag(
    "consent",
    "default",
    Object.assign(
      { analytics_storage: "denied", region: CONSENT_REGIONS, wait_for_update: 500 },
      noAds
    )
  );

  // ?internal=1 marks this browser as ours until ?internal=0: its hits carry
  // traffic_type "internal", which GA's "Internal traffic" filter drops.
  var url = new URL(window.location.href);
  var flag = url.searchParams.get("internal");
  var internal = flag === "1";
  try {
    if (flag === "1") window.localStorage.setItem("mmdc-internal", "1");
    if (flag === "0") window.localStorage.removeItem("mmdc-internal");
    internal = window.localStorage.getItem("mmdc-internal") === "1";
  } catch (e) {
    // Storage blocked: only this page load counts as internal.
  }
  if (flag !== null) {
    url.searchParams.delete("internal");
    // A copied link must not mark whoever opens it.
    try {
      window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
    } catch (e) {
      // Not allowed here.
    }
  }
  if (internal) gtag("set", { traffic_type: "internal" });
})();
