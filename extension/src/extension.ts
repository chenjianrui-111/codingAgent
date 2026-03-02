import * as vscode from "vscode";

const fetchAny: any = (globalThis as any).fetch ?? require("node-fetch");

type SessionResponse = {
  session_id: string;
  status: string;
};

type GenerateResponse = {
  answer: string;
};

type AttachmentInput = {
  kind: "image" | "audio" | "document" | "text";
  path: string;
};

function guessAttachmentKind(path: string): AttachmentInput["kind"] {
  const lowered = path.toLowerCase();
  if (/\.(png|jpg|jpeg|bmp|webp)$/.test(lowered)) {
    return "image";
  }
  if (/\.(mp3|wav|m4a|aac|flac|ogg)$/.test(lowered)) {
    return "audio";
  }
  if (/\.(txt|md|log|json|yaml|yml)$/.test(lowered)) {
    return "text";
  }
  return "document";
}

function parseAttachments(input: string | undefined): AttachmentInput[] {
  if (!input) {
    return [];
  }
  return input
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.length > 0)
    .map((path) => ({ kind: guessAttachmentKind(path), path }));
}

function currentFilePath(): string | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return undefined;
  }
  const uri = editor.document.uri;
  const folder = vscode.workspace.getWorkspaceFolder(uri);
  if (!folder) {
    return undefined;
  }
  return vscode.workspace.asRelativePath(uri, false).replace(/\\\\/g, "/");
}

async function ensureSession(context: vscode.ExtensionContext): Promise<string> {
  const cfg = vscode.workspace.getConfiguration("codingAgent");
  const baseUrl = cfg.get<string>("baseUrl") ?? "http://127.0.0.1:8080/api/v1";

  const existing = context.globalState.get<string>("codingAgent.sessionId");
  if (existing) {
    return existing;
  }

  const payload = {
    influencer_name: cfg.get<string>("influencerName") ?? "local_developer",
    category: cfg.get<string>("category") ?? "engineering",
  };

  const resp = await fetchAny(`${baseUrl}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    throw new Error(`create session failed: ${resp.status}`);
  }

  const data = (await resp.json()) as SessionResponse;
  await context.globalState.update("codingAgent.sessionId", data.session_id);
  return data.session_id;
}

export function activate(context: vscode.ExtensionContext): void {
  const disposable = vscode.commands.registerCommand("codingAgent.ask", async () => {
    const cfg = vscode.workspace.getConfiguration("codingAgent");
    const baseUrl = cfg.get<string>("baseUrl") ?? "http://127.0.0.1:8080/api/v1";

    const query = await vscode.window.showInputBox({
      prompt: "Describe the coding task for the agent",
      placeHolder: "Fix flaky test in auth module",
    });
    if (!query) {
      return;
    }

    try {
      const sessionId = await ensureSession(context);
      const currentFile = currentFilePath();
      const attachmentInput = await vscode.window.showInputBox({
        prompt: "Optional: attach file paths (comma-separated), e.g. docs/ui.png, notes/voice.mp3",
        placeHolder: "Leave empty if no attachments",
      });
      const attachments = parseAttachments(attachmentInput);
      const resp = await fetchAny(`${baseUrl}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          query,
          current_file: currentFile,
          attachments,
        }),
      });

      if (!resp.ok) {
        throw new Error(`generate failed: ${resp.status}`);
      }

      const data = (await resp.json()) as GenerateResponse;
      const doc = await vscode.workspace.openTextDocument({
        content: data.answer,
        language: "markdown",
      });
      await vscode.window.showTextDocument(doc, { preview: false });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      vscode.window.showErrorMessage(`Coding Agent error: ${msg}`);
    }
  });

  context.subscriptions.push(disposable);
}

export function deactivate(): void {
  // no-op
}
