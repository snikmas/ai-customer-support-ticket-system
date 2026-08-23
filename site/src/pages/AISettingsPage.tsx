import { useEffect, useMemo, useState } from "react";
import { apiRequest, toErrorMessage } from "../api/client";
import type { AIProvider, AIProviderTestResult, AISettings } from "../api/types";
import { StatePanel } from "../components/StatePanel";
import { useToast } from "../components/ToastContext";

const providerLabels: Record<AIProvider, string> = {
  fake: "Fake (local)",
  openrouter: "OpenRouter",
  deepseek: "Direct DeepSeek",
};

export function AISettingsPage() {
  const { notify } = useToast();
  const [settings, setSettings] = useState<AISettings | null>(null);
  const [provider, setProvider] = useState<AIProvider>("fake");
  const [model, setModel] = useState("deterministic-fake-v1");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"save" | "test" | "">("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState<AIProviderTestResult | null>(null);

  const selectedCapability = useMemo(
    () => settings?.providers.find((item) => item.provider === provider) || null,
    [provider, settings],
  );

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const loaded = await apiRequest<AISettings>("/ai-settings/");
      setSettings(loaded);
      setProvider(loaded.provider);
      setModel(loaded.model);
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const changeProvider = (next: AIProvider) => {
    setProvider(next);
    const capability = settings?.providers.find((item) => item.provider === next);
    setModel(capability?.default_model || "");
    setTestResult(null);
  };

  const save = async () => {
    if (!settings) return;
    setBusy("save");
    setError("");
    try {
      const updated = await apiRequest<AISettings>("/ai-settings/", {
        method: "PATCH",
        body: { provider, model, expected_version: settings.version },
      });
      setSettings(updated);
      setTestResult(null);
      notify("AI settings saved for new analyses.");
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const test = async () => {
    setBusy("test");
    setError("");
    try {
      const result = await apiRequest<AIProviderTestResult>("/ai-settings/test", {
        method: "POST",
        body: { provider, model },
      });
      setTestResult(result);
      if (result.ok) notify("Synthetic provider test completed.");
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  if (loading) return <StatePanel kind="loading" title="Loading AI settings" message="Reading the global provider selection…" />;
  if (error && !settings) return <StatePanel kind="forbidden" title="AI settings unavailable" message={error} action={<button className="button secondary" onClick={() => void load()}>Try again</button>} />;
  if (!settings) return null;

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>AI settings</h1>
          <p>Choose the provider for new analyses. Queued analyses keep their original provenance.</p>
        </div>
      </div>
      {error && <div className="alert error" role="alert">{error}</div>}
      <div className="settings-grid ai-settings-grid">
        <section className="card settings-card">
          <div className="card-heading-row"><div><h2>Active provider</h2><p className="muted">Version {settings.version} · updated {new Date(settings.updated_at).toLocaleString()}</p></div><span className={`status-chip ${selectedCapability?.configuration_status || "unavailable"}`}>{selectedCapability?.configuration_status || "unavailable"}</span></div>
          <label>Provider<select value={provider} onChange={(event) => changeProvider(event.target.value as AIProvider)}><option value="fake">{providerLabels.fake}</option><option value="openrouter">{providerLabels.openrouter}</option><option value="deepseek">{providerLabels.deepseek}</option></select></label>
          <label>Model<select value={model} onChange={(event) => setModel(event.target.value)}>{(selectedCapability?.selectable_models || []).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <p className="privacy-note"><strong>Privacy:</strong> {selectedCapability?.privacy_notice}</p>
          <p className="muted">Provider keys stay in server environment configuration and are never shown here.</p>
          <div className="settings-actions"><button className="button primary" onClick={() => void save()} disabled={busy !== ""}>{busy === "save" ? "Saving…" : "Save selection"}</button><button className="button secondary" onClick={() => void test()} disabled={busy !== ""}>{busy === "test" ? "Testing…" : "Test provider"}</button></div>
        </section>
        <section className="card settings-card">
          <h2>Provider test</h2>
          <p className="muted">The test uses fixed synthetic ticket content and does not change the active selection.</p>
          {testResult ? <div className={`test-result ${testResult.ok ? "success" : "failure"}`} role="status"><strong>{testResult.ok ? "Test passed" : "Test failed"}</strong><span>{testResult.provider} · {testResult.model}</span>{testResult.safe_error_code && <span>Safe error: {testResult.safe_error_code}</span>}{testResult.ok && <span>Tokens: {testResult.input_tokens ?? "—"} in / {testResult.output_tokens ?? "—"} out</span>}</div> : <div className="empty-inline">No provider test has run in this session.</div>}
          <div className="settings-note"><strong>External providers:</strong> use synthetic data only. Direct DeepSeek does not receive an equivalent request-level ZDR claim.</div>
        </section>
      </div>
    </>
  );
}
