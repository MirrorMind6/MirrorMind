// diff.js — Line-by-line diff using Longest Common Subsequence.
// Same algorithm as Git's diff output.

const Diff = {

  // Returns array of { type: 'added'|'removed'|'unchanged', text: string }
  compute(oldText, newText) {
    const a = (oldText || '').split('\n');
    const b = (newText || '').split('\n');
    return lcs(a, b);
  },

  // Short summary string: "+3 / -1 lines", "No changes", etc.
  stats(oldText, newText) {
    const lines   = this.compute(oldText, newText);
    const added   = lines.filter(l => l.type === 'added').length;
    const removed = lines.filter(l => l.type === 'removed').length;
    if (added === 0 && removed === 0) return 'No changes';
    if (removed === 0) return `+${added} line${added !== 1 ? 's' : ''}`;
    if (added === 0)   return `-${removed} line${removed !== 1 ? 's' : ''}`;
    return `+${added} / -${removed} lines`;
  },

};

function lcs(a, b) {
  const m = a.length, n = b.length;
  // Build DP table
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i-1] === b[j-1] ? dp[i-1][j-1] + 1 : Math.max(dp[i-1][j], dp[i][j-1]);

  // Backtrack
  const result = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i-1] === b[j-1]) {
      result.push({ type: 'unchanged', text: a[i-1] }); i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j-1] >= dp[i-1][j])) {
      result.push({ type: 'added',     text: b[j-1] }); j--;
    } else {
      result.push({ type: 'removed',   text: a[i-1] }); i--;
    }
  }
  return result.reverse();
}
