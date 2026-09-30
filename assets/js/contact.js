/* Contact page: submit the form to Formspree without its JS library, using
   plain fetch. The <form> keeps its own action/method as a no-JS fallback
   (a native POST redirects to Formspree's own thank-you page), so everything
   here is progressive enhancement, not the only way the form can work.

   _gotcha is Formspree's own documented honeypot field name: they silently
   discard a submission that arrives with it filled, so no client-side
   honeypot check is needed here.

   Nothing is fetched at runtime except the form's own POST on submit. */
(function () {
  "use strict";

  var form = document.getElementById("cf-form");
  if (!form) return;

  var submit = document.getElementById("cf-submit");
  var error = document.getElementById("cf-error");
  var success = document.getElementById("cf-success");
  var subjectField = document.getElementById("cf-subject");
  if (!submit || !error || !success || !subjectField) return;

  var SENDING_LABEL = "Sending…";
  var ORIGINAL_LABEL = submit.textContent;

  function setSubject() {
    var topic = (form.elements.topic && form.elements.topic.value) || "";
    var first = (form.elements.first_name && form.elements.first_name.value || "").trim();
    var last = (form.elements.last_name && form.elements.last_name.value || "").trim();
    var name = (first + " " + last).trim();
    subjectField.value = "[Website] " + (name ? topic + ": " + name : topic || "Contact form");
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();

    // Native HTML validation first: required fields, and the email type,
    // catch an incomplete form before anything is sent. reportValidity()
    // still shows the browser's own validation bubbles even though the
    // default submit was already prevented above.
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    error.hidden = true;
    setSubject();

    // The addressing field's own default option value is now the literal
    // string "No preference", so nothing needs substituting here the way an
    // empty value once did.
    var data = new FormData(form);

    submit.disabled = true;
    submit.textContent = SENDING_LABEL;

    fetch(form.action, {
      method: "POST",
      body: data,
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Form submission failed");
        form.hidden = true;
        success.hidden = false;
        // Scroll to the top rather than pinning the form's height: on a
        // long form the reader may be scrolled well down the page, and the
        // short success row taking the form's place would otherwise leave
        // them looking at empty space below it. focus() runs with
        // preventScroll so it cannot re-introduce a scroll of its own once
        // this one has already put the success row in view.
        window.scrollTo(0, 0);
        success.focus({ preventScroll: true });
      })
      .catch(function () {
        error.hidden = false;
        submit.disabled = false;
        submit.textContent = ORIGINAL_LABEL;
      });
  });
})();
