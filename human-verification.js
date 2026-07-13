function createHumanVerification() {
  function setDisabled(selector, disabled) {
    if (!selector) return;
    document.querySelectorAll(selector).forEach((element) => {
      element.querySelectorAll("button, input, select, textarea, a").forEach((control) => {
        if (disabled) {
          control.dataset.humanDisabled = "1";
          if ("disabled" in control) {
            control.disabled = true;
          }
          if (control.tagName === "A") {
            control.setAttribute("aria-disabled", "true");
            control.tabIndex = -1;
          }
        } else if (control.dataset.humanDisabled === "1") {
          delete control.dataset.humanDisabled;
          if ("disabled" in control) {
            control.disabled = false;
          }
          if (control.tagName === "A") {
            control.removeAttribute("aria-disabled");
            control.tabIndex = 0;
          }
        }
      });
    });
  }

  async function requestJson(url, options) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "请求失败");
    }
    return payload;
  }

  async function init(options) {
    const {
      overlayId,
      checkboxId,
      buttonId,
      messageId,
      gateSelector,
      onVerified
    } = options;

    const overlay = document.getElementById(overlayId);
    const checkbox = document.getElementById(checkboxId);
    const button = document.getElementById(buttonId);
    const message = document.getElementById(messageId);

    if (!overlay || !checkbox || !button || !message) {
      throw new Error("人机验证组件未正确挂载。");
    }

    function setMessage(text, isError = false) {
      message.textContent = text;
      message.classList.toggle("is-error", isError);
    }

    function openGate(text) {
      setDisabled(gateSelector, true);
      checkbox.checked = false;
      button.disabled = true;
      overlay.classList.add("is-active");
      setMessage(text || "勾选后即可继续访问。");
    }

    function closeGate() {
      overlay.classList.remove("is-active");
      setDisabled(gateSelector, false);
      setMessage("");
    }

    checkbox.addEventListener("change", () => {
      button.disabled = !checkbox.checked;
      if (checkbox.checked) {
        setMessage("点击下方按钮完成验证。");
      } else {
        setMessage("勾选后即可继续访问。");
      }
    });

    button.addEventListener("click", async () => {
      if (!checkbox.checked) {
        button.disabled = true;
        return;
      }
      button.disabled = true;
      setMessage("正在验证...");
      try {
        await requestJson("/api/human-verify", { method: "POST" });
        closeGate();
        if (typeof onVerified === "function") {
          onVerified();
        }
      } catch (error) {
        setMessage(error.message || "验证失败，请稍后重试。", true);
        button.disabled = false;
      }
    });

    try {
      const status = await requestJson("/api/human-status");
      if (status.verified) {
        closeGate();
        if (typeof onVerified === "function") {
          onVerified();
        }
        return;
      }
    } catch (error) {
      openGate("验证状态检查失败，请重新勾选后继续。");
      setMessage(error.message || "验证状态检查失败，请重新勾选后继续。", true);
      return;
    }

    openGate("勾选后即可继续访问。");
  }

  return { init };
}

window.humanVerification = createHumanVerification();
