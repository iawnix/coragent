const ADMONITION_RE = /^>\s*\[\s*!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\s*\]\s*(.*)$/i;
const URL_RE = /https?:\/\/[^\s<>'"|，。；：！？、」』】（）【】《》『』「」]+/g;
const URL_TRAILING_PUNCTUATION_RE = /[.,;:!?】」』"'》）}]+$/;
const CIRCLED_RE = /[①-⑳]/g;

function trimUrl(url) {
  let result = url.replace(URL_TRAILING_PUNCTUATION_RE, "");
  for (;;) {
    if (result.endsWith(")") && (result.match(/\(/g)?.length ?? 0) < (result.match(/\)/g)?.length ?? 0)) {
      result = result.slice(0, -1);
      continue;
    }
    if (result.endsWith("]") && (result.match(/\[/g)?.length ?? 0) < (result.match(/\]/g)?.length ?? 0)) {
      result = result.slice(0, -1);
      continue;
    }
    return result;
  }
}

function isFence(line) {
  return /^\s*(`{3,}|~{3,})/.test(line);
}

function linkifyText(text) {
  return text.replace(URL_RE, (url, offset, source) => {
    const prefix = source.slice(Math.max(0, offset - 2), offset);
    const suffix = source.slice(offset + url.length);
    if (prefix.endsWith("](") || prefix.endsWith("<") || suffix.startsWith("](")) return url;
    const target = trimUrl(url);
    return target ? `[${target}](${target})${url.slice(target.length)}` : url;
  });
}

/** Convert bare URLs outside fenced blocks and inline code spans into Markdown links. */
export function linkifyBareUrls(markdown) {
  const lines = String(markdown).split("\n");
  const output = [];
  let fence = false;
  for (const line of lines) {
    if (isFence(line)) {
      fence = !fence;
      output.push(line);
      continue;
    }
    if (fence) {
      output.push(line);
      continue;
    }
    const parts = line.split("`");
    for (let index = 0; index < parts.length; index++) {
      if (index % 2 === 0) parts[index] = linkifyText(parts[index]);
    }
    output.push(parts.join("`"));
  }
  return output.join("\n");
}

/** Convert GitHub-style admonitions to readable, font-safe Markdown labels. */
export function enhanceAdmonitions(markdown) {
  const lines = String(markdown).split("\n");
  const output = [];
  let fence = false;
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (isFence(line)) {
      fence = !fence;
      output.push(line);
      index++;
      continue;
    }
    const match = !fence ? line.match(ADMONITION_RE) : null;
    if (!match) {
      output.push(line);
      index++;
      continue;
    }

    const body = [match[2]];
    let next = index + 1;
    while (next < lines.length && /^>\s?/.test(lines[next]) && !ADMONITION_RE.test(lines[next])) {
      body.push(lines[next].replace(/^>\s?/, ""));
      next++;
    }
    while (body.length > 0 && body.at(-1).trim() === "") body.pop();
    const label = match[1].toUpperCase();
    const content = body.join(" ").replace(/\s+/g, " ").trim();
    output.push(`> **[${label}]**${content ? ` ${content}` : ""}`);
    if (next < lines.length && lines[next].trim() !== "") output.push("");
    index = next;
  }
  return output.join("\n");
}

export function normalizeCircledNumbers(markdown) {
  const lines = String(markdown).split("\n");
  const output = [];
  let fence = false;
  for (const line of lines) {
    if (isFence(line)) {
      fence = !fence;
      output.push(line);
      continue;
    }
    if (fence) {
      output.push(line);
      continue;
    }
    const parts = line.split("`");
    for (let index = 0; index < parts.length; index++) {
      if (index % 2 === 0) {
        parts[index] = parts[index].replace(CIRCLED_RE, character => `(${character.codePointAt(0) - 0x2460 + 1})`);
      }
    }
    output.push(parts.join("`"));
  }
  return output.join("\n");
}

/** Apply stable presentation transforms while preserving streaming and thinking content. */
export function enhanceMarkdown(markdown, context = {}) {
  if (context.messageType === "assistant-thinking" || context.isStreaming) return markdown;
  return linkifyBareUrls(enhanceAdmonitions(normalizeCircledNumbers(markdown)));
}

