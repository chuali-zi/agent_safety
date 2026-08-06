/* XA-Guard Live Workbench 前端逻辑
 * 纪律：UI 只渲染 API 返回的真实 event/artifact；不自行判定 allow/deny/harm；
 * 无 audit 的 Gate 保持 UNKNOWN/NOT_REACHED；MODEL_SELF_DEFENSE 不算 Guard win。
 */
(function () {
  "use strict";

  var state = {
    runId: null,
    runMode: null,
    afterSeq: 0,
    pollTimer: null,
    intentArgsSha: null,
    intentWorldSha: null,
    nullResult: null,
    guardResult: null,
    transcriptLoaded: false,
    hitlPhase: null
  };

  function $(id) { return document.getElementById(id); }

  function shortHash(hash) {
    if (!hash || hash.length < 24) return hash || "—";
    return hash.slice(0, 12) + "…" + hash.slice(-8);
  }

  function hashSpan(hash) {
    var span = document.createElement("span");
    span.className = "hash";
    span.textContent = shortHash(hash);
    span.title = hash || "";
    span.onclick = function () { alert(hash); };
    return span;
  }

  function setHash(id, hash) {
    var el = $(id);
    if (!el) return;
    el.textContent = "";
    el.appendChild(hashSpan(hash));
  }

  function setTag(id, text, cls) {
    var el = $(id);
    el.textContent = text;
    el.className = "tag " + cls;
  }

  function setBadge(mode) {
    var badge = $("mode-badge");
    badge.className = "";
    if (mode === "LIVE_RUN") { badge.textContent = "LIVE RUN"; badge.classList.add("live"); }
    else if (mode === "SEALED_REPLAY") { badge.textContent = "SEALED REPLAY"; badge.classList.add("sealed"); }
    else if (mode === "EXAMPLE_SYNTHETIC") { badge.textContent = "EXAMPLE / SYNTHETIC"; badge.classList.add("synthetic"); }
    else { badge.textContent = "IDLE"; }
    $("corner-run").textContent = (state.runId || "idle") + " · " + (mode || "");
  }

  function api(method, path, body) {
    return fetch(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (resp) {
      return resp.json().then(function (data) {
        if (!resp.ok) throw new Error(data.error || ("HTTP " + resp.status));
        return data;
      });
    });
  }

  /* ---------- 场景列表 ---------- */
  function loadScenarios() {
    api("GET", "/api/live/scenarios").then(function (data) {
      var sel = $("scenario-select");
      sel.innerHTML = "";
      var gLive = document.createElement("optgroup");
      gLive.label = "LIVE RUN（真实模型 + 真实 XA-Guard）";
      (data.live_cases || []).forEach(function (c) {
        var opt = document.createElement("option");
        opt.value = "live:" + c;
        opt.textContent = "LIVE · " + c;
        gLive.appendChild(opt);
      });
      sel.appendChild(gLive);
      (data.sealed_packs || []).forEach(function (pack) {
        var g = document.createElement("optgroup");
        g.label = "SEALED REPLAY · " + pack.pack;
        var sorted = (pack.runs || []).slice().sort(function (a, b) {
          return (b.attempt ? 1 : 0) - (a.attempt ? 1 : 0);
        });
        sorted.slice(0, 15).forEach(function (r) {
          var opt = document.createElement("option");
          opt.value = "sealed:" + pack.pack + "/" + r.case_id + "/" + r.prompt_profile + "/" + r.run_name;
          opt.textContent = r.case_id + " · " + r.prompt_profile + " · " + r.run_name +
            (r.attempt ? " · " + (r.guard_decision || "?") : " · self-defense");
          g.appendChild(opt);
        });
        sel.appendChild(g);
      });
      var gSyn = document.createElement("optgroup");
      gSyn.label = "EXAMPLE / SYNTHETIC（合成演示，非证据）";
      var labels = {
        d2: "D2 攻击阻断演示",
        utility: "安全正例（非 deny-all）",
        hitl: "HITL 审批 + replay 拒绝",
        verifier: "verifier PASS / 篡改副本 FAIL"
      };
      (data.synthetic || []).forEach(function (s) {
        var opt = document.createElement("option");
        opt.value = "synthetic:" + s;
        opt.textContent = "DEMO · " + (labels[s] || s);
        gSyn.appendChild(opt);
      });
      sel.appendChild(gSyn);
    }).catch(function (err) {
      $("run-detail").textContent = "场景列表加载失败：" + err.message;
    });
  }

  /* ---------- 渲染 ---------- */
  function renderGate(gate) {
    var box = document.querySelector('.gate[data-gate="' + gate.gate_id + '"]');
    if (!box) return;
    box.className = "gate st-" + gate.status;
    box.querySelector(".gstatus").textContent = gate.status;
    // 幂等：清掉旧的 hash/rules 节点再重画
    box.querySelectorAll(".ghash").forEach(function (n) { n.remove(); });
    var hashEl = document.createElement("div");
    hashEl.className = "ghash";
    if (gate.audit_record_hash) hashEl.appendChild(hashSpan(gate.audit_record_hash));
    box.appendChild(hashEl);
    if (gate.gate_id === "GATE6" && gate.audit_record_hash) {
      setHash("guard-audit", gate.audit_record_hash);
    }
    if (gate.rule_ids && gate.rule_ids.length) {
      var rules = document.createElement("div");
      rules.className = "ghash";
      rules.textContent = gate.rule_ids.join(", ");
      box.appendChild(rules);
    }
  }

  function renderBranchResult(prefix, result) {
    var decisionEl = $(prefix + "-decision");
    decisionEl.textContent = result.decision || "—";
    decisionEl.style.color = result.decision === "deny" ? "var(--deny)" :
      result.decision === "allow" ? "var(--allow)" : "";
    $(prefix + "-downstream").textContent = String(result.downstream_call_count);
    var harm = result.harm_observed;
    $(prefix + "-harm").textContent = harm ? "HARM" : "0";
    $(prefix + "-harm").style.color = harm ? "var(--deny)" : "var(--allow)";
    setHash(prefix + "-world-before", result.world_before_sha256);
    setHash(prefix + "-world-after", result.world_after_sha256);
    var ledger = $(prefix + "-ledger");
    if (ledger && result.ledger_sha256) setHash(prefix + "-ledger", result.ledger_sha256);
  }

  function causalSet(id, ok, text) {
    var el = $(id);
    el.className = "causal-item " + (ok === null ? "" : ok ? "ok" : "bad");
    el.querySelector(".big").textContent = text;
  }

  function updateCausal() {
    if (!state.nullResult || !state.guardResult || !state.intentArgsSha) return;
    var sameIntent = state.nullResult.intent_arguments_sha256 === state.guardResult.intent_arguments_sha256 &&
      state.nullResult.intent_arguments_sha256 === state.intentArgsSha;
    var sameWorld = state.nullResult.world_before_sha256 === state.guardResult.world_before_sha256 &&
      state.nullResult.world_before_sha256 === state.intentWorldSha;
    causalSet("c-intent", sameIntent, sameIntent ? "✓" : "✗");
    causalSet("c-world", sameWorld, sameWorld ? "✓" : "✗");
    var onlySutChanged = sameIntent && sameWorld;
    causalSet("c-sut", onlySutChanged, onlySutChanged ? "✓" : "✗");
    if (!onlySutChanged) {
      $("causal").classList.add("invalid");
      var v = $("causal-verdict");
      v.textContent = "INVALID_COMPARISON";
      v.className = "tag deny";
      return;
    }
    var harmText = (state.nullResult.harm_observed ? "1" : "0") + " → " + (state.guardResult.harm_observed ? "1" : "0");
    causalSet("c-harm", !state.guardResult.harm_observed, harmText);
    var dsText = state.nullResult.downstream_call_count + " → " + state.guardResult.downstream_call_count;
    var downstreamSafe = ["deny", "pending"].indexOf(state.guardResult.decision) < 0 ||
      state.guardResult.downstream_call_count === 0;
    causalSet("c-downstream", downstreamSafe, dsText);
    var verdict = $("causal-verdict");
    if (state.guardResult.decision === "deny" && !state.guardResult.harm_observed && state.nullResult.harm_observed) {
      verdict.textContent = "同一 intent：Null harm，Guard deny / 0 harm";
      verdict.className = "tag deny";
    } else if (state.guardResult.decision === "allow" && !state.nullResult.harm_observed) {
      verdict.textContent = "安全正例：双臂 allow（非 deny-all）";
      verdict.className = "tag allow";
    } else {
      verdict.textContent = "";
    }
  }

  function addArtifacts(refs) {
    if (!refs) return;
    if (!state.seenArtifacts) state.seenArtifacts = {};
    var list = $("artifact-list");
    refs.forEach(function (ref) {
      var key = ref.name + " " + ref.json_pointer;
      if (state.seenArtifacts[key]) return;
      state.seenArtifacts[key] = true;
      var chip = document.createElement("span");
      chip.className = "artifact-chip";
      chip.textContent = ref.name + " " + ref.json_pointer;
      chip.title = ref.sha256;
      chip.onclick = function () { openArtifact(ref); };
      list.appendChild(chip);
    });
  }

  function openArtifact(ref) {
    if (!state.runId) return;
    api("GET", "/api/live/artifact?run_id=" + encodeURIComponent(state.runId) +
      "&name=" + encodeURIComponent(ref.name) + "&sha256=" + encodeURIComponent(ref.sha256)).then(function (env) {
      $("modal-title").textContent = env.name + " " + ref.json_pointer + " · sha256 " + shortHash(env.sha256);
      $("modal-body").textContent = JSON.stringify(env.data, null, 2);
      $("modal").classList.add("show");
    }).catch(function (err) {
      alert("artifact 读取失败：" + err.message);
    });
  }

  function loadTranscript(ref) {
    if (state.runMode === "EXAMPLE_SYNTHETIC") return;
    if (state.transcriptLoaded || state.transcriptLoading || !state.runId || !ref) return;
    state.transcriptLoading = true;
    api("GET", "/api/live/artifact?run_id=" + encodeURIComponent(state.runId) +
      "&name=agent-transcript.jsonl&sha256=" + encodeURIComponent(ref.sha256)).then(function (env) {
      state.transcriptLoaded = true;
      var box = $("transcript");
      box.innerHTML = "";
      (env.data.lines || []).forEach(function (line) {
        var div = document.createElement("div");
        div.className = "transcript-line";
        var role = document.createElement("span");
        role.className = "role " + String(line.role || "");
        role.textContent = (line.turn !== undefined ? "t" + line.turn + " " : "") + (line.role || "?");
        var text = document.createElement("span");
        var content = line.content;
        if (typeof content !== "string") content = JSON.stringify(content || line.name || line.violating || "");
        if (content.length > 220) content = content.slice(0, 220) + "…";
        text.textContent = " " + content;
        div.appendChild(role);
        div.appendChild(text);
        box.appendChild(div);
      });
      setTag("transcript-hint", "已加载", "info");
      box.scrollTop = box.scrollHeight;
    }).catch(function () {
      if (!state.completed) setTag("transcript-hint", "无 transcript", "gray");
    }).finally(function () { state.transcriptLoading = false; });
  }

  function showOperatorCard(phase) {
    state.hitlPhase = phase;
    var card = $("operator-card");
    if (!phase) { card.classList.remove("show"); return; }
    card.classList.add("show");
    $("btn-approve").style.display = phase === "pending" ? "" : "none";
    $("btn-reject").style.display = phase === "pending" ? "" : "none";
    $("btn-replay").style.display = phase === "replay" ? "" : "none";
    $("operator-msg").textContent = phase === "pending"
      ? "pending 审批：Dora 以独立身份/独立通道批准；Agent/Alice 不能自批。"
      : "点击 replay 重放：同 trace 重放应被 Gate2 拒绝（token 一次消费）。";
  }

  /* ---------- 事件处理 ---------- */
  function handleEvent(ev) {
    $("run-detail").textContent = (ev.message || ev.event_type) + " · state=" + ev.state;
    addArtifacts(ev.artifact_refs);

    switch (ev.event_type) {
      case "PREFLIGHT_FAILED":
        setTag("transcript-hint", "PREFLIGHT_FAILED", "fail");
        break;
      case "MODEL_RESPONDED":
        loadTranscript((ev.artifact_refs || []).find(function (ref) {
          return ref.name === "agent-transcript.jsonl";
        }));
        break;
      case "MODEL_SELF_DEFENSE":
        setTag("intent-hint", "MODEL_SELF_DEFENSE（不是 Guard win）", "info");
        break;
      case "INTENT_FROZEN":
        if (ev.intent) {
          state.intentArgsSha = ev.intent.arguments_sha256;
          state.intentWorldSha = ev.intent.world_before_sha256;
          $("intent-tool").textContent = ev.intent.tool_name;
          setHash("intent-args", ev.intent.arguments_sha256);
          setHash("intent-world", ev.intent.world_before_sha256);
          $("intent-target").textContent = (ev.intent.property_id || "") + " / " + (ev.intent.target_summary || "");
          setTag("intent-hint", "已冻结", "info");
        }
        break;
      case "NULL_STARTED":
        setTag("null-hint", "RUNNING", "info");
        break;
      case "NULL_COMPLETED":
        if (ev.branch_result) {
          state.nullResult = ev.branch_result;
          renderBranchResult("null", ev.branch_result);
          setTag("null-hint", ev.branch_result.harm_observed ? "HARM" : "COMPLETE",
            ev.branch_result.harm_observed ? "harm" : "allow");
        }
        break;
      case "GUARD_STARTED":
        setTag("guard-hint", "RUNNING", "info");
        break;
      case "GUARD_GATE_RESULT":
        if (ev.gate) renderGate(ev.gate);
        if (ev.state === "PENDING_APPROVAL" && state.runMode === "EXAMPLE_SYNTHETIC") {
          showOperatorCard("pending");
        }
        break;
      case "GUARD_PENDING_APPROVAL":
        setTag("guard-hint", "PENDING_APPROVAL", "warn");
        if (state.runMode === "EXAMPLE_SYNTHETIC") showOperatorCard("pending");
        break;
      case "OPERATOR_APPROVED":
        setTag("guard-hint", "APPROVED → 重验证", "allow");
        showOperatorCard(null);
        break;
      case "OPERATOR_REJECTED":
        setTag("guard-hint", "REJECTED / replay deny", "deny");
        showOperatorCard(null);
        break;
      case "GUARD_COMPLETED":
        if (ev.branch_result) {
          state.guardResult = ev.branch_result;
          renderBranchResult("guard", ev.branch_result);
          var d = ev.branch_result.decision;
          setTag("guard-hint", String(d).toUpperCase(), d === "deny" ? "deny" : d === "allow" ? "allow" : "gray");
          if (ev.branch_result.decision === "allow" && state.hitlPhase === "approved-wait-replay") {
            showOperatorCard("replay");
          }
        }
        if (state.runMode === "EXAMPLE_SYNTHETIC" && state.hitlPhase === "approved") {
          showOperatorCard("replay");
        }
        break;
      case "VERIFY_COMPLETED":
        if (ev.verification) renderVerificationEvent(ev.verification);
        break;
      case "RUN_COMPLETED":
        state.completed = true;
        setTag("transcript-hint", "COMPLETE", "allow");
        if (state.hitlPhase === "approved" && state.runMode === "EXAMPLE_SYNTHETIC") showOperatorCard(null);
        break;
      case "RUN_FAILED":
        state.completed = true;
        setTag("transcript-hint", "FAILED", "fail");
        break;
    }
    updateCausal();
  }

  function renderVerificationEvent(v) {
    var el = $("verify-result");
    el.innerHTML = "";
    var tag = document.createElement("span");
    tag.className = "tag " + (v.ok ? "allow" : "fail");
    tag.textContent = v.target + ": " + (v.ok ? "PASS" : "FAIL") +
      (v.failed_checks && v.failed_checks.length ? " (" + v.failed_checks.join(", ") + ")" : "");
    el.appendChild(tag);
  }

  /* ---------- 轮询 ---------- */
  function poll() {
    if (!state.runId || state.polling) return;
    state.polling = true;
    api("GET", "/api/live/events?run_id=" + encodeURIComponent(state.runId) +
      "&after_seq=" + state.afterSeq).then(function (data) {
      data.events.forEach(function (event) {
        try {
          handleEvent(event);
        } catch (err) {
          console.error("event render failed", event.sequence, event.event_type, err);
        }
      });
      state.afterSeq = data.next_after_seq || state.afterSeq;
    }).catch(function () { /* 轮询失败静默重试 */ })
      .finally(function () { state.polling = false; });
  }

  function resetUI(mode) {
    state.runId = null;
    state.runMode = mode;
    state.afterSeq = 0;
    state.intentArgsSha = null;
    state.intentWorldSha = null;
    state.nullResult = null;
    state.guardResult = null;
    state.transcriptLoaded = false;
    state.transcriptLoading = false;
    state.completed = false;
    state.hitlPhase = null;
    state.seenArtifacts = {};
    $("transcript").innerHTML = "";
    $("artifact-list").innerHTML = "";
    $("verify-result").innerHTML = "";
    $("verify-checks").innerHTML = "";
    ["intent-tool", "intent-target"].forEach(function (id) { $(id).textContent = "—"; });
    ["intent-args", "intent-world", "null-world-before", "null-world-after", "null-ledger",
      "guard-world-before", "guard-world-after", "guard-audit"].forEach(function (id) { $(id).textContent = "—"; });
    ["null-decision", "null-downstream", "null-harm", "guard-decision", "guard-downstream", "guard-harm"]
      .forEach(function (id) { $(id).textContent = "—"; $(id).style.color = ""; });
    document.querySelectorAll(".gate").forEach(function (g) {
      g.className = "gate st-UNKNOWN";
      g.querySelector(".gstatus").textContent = "·";
      g.querySelectorAll(".ghash").forEach(function (n) { n.remove(); });
      var empty = document.createElement("div");
      empty.className = "ghash";
      g.appendChild(empty);
    });
    ["c-intent", "c-world", "c-sut", "c-harm", "c-downstream"].forEach(function (id) {
      causalSet(id, null, "?");
    });
    $("causal").classList.remove("invalid");
    $("causal-verdict").textContent = "";
    setTag("transcript-hint", "等待", "gray");
    setTag("intent-hint", "未冻结", "gray");
    setTag("null-hint", "NOT_REACHED", "gray");
    setTag("guard-hint", "NOT_REACHED", "gray");
    showOperatorCard(null);
    var sealed = mode === "SEALED_REPLAY";
    $("btn-verify").disabled = !sealed;
    $("btn-tamper").disabled = !sealed;
    setTag("verify-hint", sealed ? "可验证当前包" : "仅 SEALED 可用", "gray");
  }

  /* ---------- 动作 ---------- */
  $("btn-run").onclick = function () {
    var scenarioId = $("scenario-select").value;
    if (!scenarioId) return;
    var mode = scenarioId.indexOf("live:") === 0 ? "LIVE_RUN" :
      scenarioId.indexOf("sealed:") === 0 ? "SEALED_REPLAY" : "EXAMPLE_SYNTHETIC";
    resetUI(mode);
    setBadge(mode);
    api("POST", "/api/live/run", { scenario_id: scenarioId, guard_mode: "live" }).then(function (accepted) {
      state.runId = accepted.run_id;
      $("run-id").textContent = accepted.run_id;
      setBadge(accepted.run_mode);
      if (state.pollTimer) clearInterval(state.pollTimer);
      state.pollTimer = setInterval(poll, 600);
      poll();
    }).catch(function (err) {
      $("run-detail").textContent = "RUN 启动失败：" + err.message;
    });
  };

  $("btn-preflight").onclick = function () {
    var scenarioId = $("scenario-select").value;
    if (!scenarioId) return;
    api("POST", "/api/live/preflight", { scenario_id: scenarioId, guard_mode: "live" }).then(function (resp) {
      var lines = resp.checks.map(function (c) {
        return (c.ok ? "✓ " : "✗ ") + c.name + (c.detail ? " — " + c.detail : "");
      });
      $("run-detail").textContent = "PREFLIGHT " + (resp.ok ? "READY" : "FAILED") + "：" + lines.join("；");
    }).catch(function (err) {
      $("run-detail").textContent = "PREFLIGHT 失败：" + err.message;
    });
  };

  $("btn-verify").onclick = function () {
    if (!state.runId) return;
    $("btn-verify").disabled = true;
    api("POST", "/api/live/verify", { run_id: state.runId }).then(function (resp) {
      renderVerificationEvent({ target: resp.target, ok: resp.ok, failed_checks: resp.checks.filter(function (c) { return !c.ok; }).map(function (c) { return c.name; }) });
      $("verify-checks").textContent = resp.checks.map(function (c) {
        return (c.ok ? "PASS " : "FAIL ") + c.name;
      }).join("\n");
    }).catch(function (err) {
      $("verify-result").textContent = "verify 失败：" + err.message;
    }).finally(function () { $("btn-verify").disabled = false; });
  };

  $("btn-tamper").onclick = function () {
    if (!state.runId) return;
    $("btn-tamper").disabled = true;
    api("POST", "/api/live/verify-tampered-copy", {
      run_id: state.runId,
      artifact_name: $("tamper-artifact").value,
      json_pointer: $("tamper-pointer").value
    }).then(function (resp) {
      renderVerificationEvent({ target: resp.target + " → 预期 FAIL", ok: resp.ok, failed_checks: resp.checks.filter(function (c) { return !c.ok; }).map(function (c) { return c.name; }) });
      $("verify-checks").textContent = resp.checks.map(function (c) {
        return (c.ok ? "PASS " : "FAIL ") + c.name;
      }).join("\n");
    }).catch(function (err) {
      $("verify-result").textContent = "tamper verify 失败：" + err.message;
    }).finally(function () { $("btn-tamper").disabled = false; });
  };

  function operatorAction(action) {
    if (!state.runId) return;
    if (action === "approve") state.hitlPhase = "approved";
    api("POST", "/api/live/operator", { run_id: state.runId, action: action }).catch(function (err) {
      $("operator-msg").textContent = "operator 通道失败：" + err.message;
    });
  }
  $("btn-approve").onclick = function () { operatorAction("approve"); };
  $("btn-reject").onclick = function () { operatorAction("reject"); };
  $("btn-replay").onclick = function () { operatorAction("replay"); showOperatorCard(null); };

  $("modal-close").onclick = function () { $("modal").classList.remove("show"); };
  $("modal").onclick = function (e) { if (e.target === $("modal")) $("modal").classList.remove("show"); };

  setBadge(null);
  loadScenarios();

  // 录屏/无头验证支持：?scenario=<scenario_id>&autorun=1 自动选择并运行
  var params = new URLSearchParams(location.search);
  if (params.get("scenario")) {
    var wanted = params.get("scenario");
    var waitLoaded = setInterval(function () {
      var sel = $("scenario-select");
      var opt = [].slice.call(sel.options).find(function (o) { return o.value === wanted; });
      if (opt) {
        clearInterval(waitLoaded);
        sel.value = wanted;
        if (params.get("autorun") === "1") $("btn-run").click();
      }
    }, 300);
    setTimeout(function () { clearInterval(waitLoaded); }, 10000);
  }
})();
