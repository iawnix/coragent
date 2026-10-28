/** Keep explicit Tab in a slash command on that command's argument provider. */
export function createCommandCompletionProvider(CombinedAutocompleteProvider, commands, cwd) {
  class CommandCompletionProvider extends CombinedAutocompleteProvider {
    getSuggestions(lines, row, column, options) {
      const text = (lines[row] || "").slice(0, column).trimStart();
      return super.getSuggestions(lines, row, column, text.startsWith("/") ? { ...options, force: false } : options);
    }
  }
  return new CommandCompletionProvider(commands, cwd);
}
