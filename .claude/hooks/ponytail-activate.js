#!/usr/bin/env node
// ponytail — Claude Code SessionStart activation hook

const fs = require('fs');
const path = require('path');
const { getDefaultMode, getClaudeDir } = require('./ponytail-config');
const { getPonytailInstructions } = require('./ponytail-instructions');
const {
  clearMode,
  isCodex,
  setMode,
  writeHookOutput,
} = require('./ponytail-runtime');

const claudeDir = getClaudeDir();
const settingsPath = path.join(claudeDir, 'settings.json');

const mode = getDefaultMode();

if (mode === 'off') {
  clearMode();
  writeHookOutput('SessionStart', 'off', isCodex ? '' : 'OK');
  process.exit(0);
}

try {
  setMode(mode);
} catch (e) {}

let output = getPonytailInstructions(mode);

if (!isCodex) try {
  let hasStatusline = false;
  if (fs.existsSync(settingsPath)) {
    const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    if (settings.statusLine) {
      hasStatusline = true;
    }
  }

  if (!hasStatusline) {
    const scriptPath = path.join(__dirname, 'ponytail-statusline.sh');
    const command = `bash "${scriptPath}"`;
    const statusLineSnippet =
      '"statusLine": { "type": "command", "command": ' + JSON.stringify(command) + ' }';
    output += "\n\nSTATUSLINE SETUP NEEDED: The ponytail plugin includes a statusline badge showing active mode " +
      "(e.g. [PONYTAIL], [PONYTAIL:ULTRA]). It is not configured yet. " +
      "To enable, add this to ~/.claude/settings.json: " +
      statusLineSnippet + " " +
      "Proactively offer to set this up for the user on first interaction.";
  }
} catch (e) {}

writeHookOutput('SessionStart', mode, output);
