import Foundation

/// Compares two framework summaries line-by-line and produces a diff
/// showing exactly what was added, removed, or left unchanged.
///
/// Uses a Longest Common Subsequence (LCS) algorithm — the same
/// core idea behind Git's diff output.
enum DiffEngine {

    enum Line: Identifiable {
        case unchanged(String)
        case added(String)
        case removed(String)

        var id: String {
            switch self {
            case .unchanged(let t): "u-\(t)"
            case .added(let t):     "a-\(t)"
            case .removed(let t):   "r-\(t)"
            }
        }

        var text: String {
            switch self { case .unchanged(let t), .added(let t), .removed(let t): t }
        }
    }

    /// Returns a line-by-line diff between `old` and `new`.
    static func diff(old: String, new: String) -> [Line] {
        let oldLines = old.components(separatedBy: "\n")
        let newLines = new.components(separatedBy: "\n")
        return lcs(oldLines, newLines)
    }

    /// Quick stats for the version row — "3 added, 1 removed"
    static func stats(old: String, new: String) -> String {
        let lines = diff(old: old, new: new)
        let added   = lines.filter { if case .added   = $0 { return true }; return false }.count
        let removed = lines.filter { if case .removed = $0 { return true }; return false }.count
        switch (added, removed) {
        case (0, 0): return "No changes"
        case (_, 0): return "+\(added) line\(added == 1 ? "" : "s")"
        case (0, _): return "-\(removed) line\(removed == 1 ? "" : "s")"
        default:     return "+\(added) / -\(removed) lines"
        }
    }

    // MARK: - LCS backtracking

    private static func lcs(_ a: [String], _ b: [String]) -> [Line] {
        let m = a.count, n = b.count
        guard m > 0 || n > 0 else { return [] }

        // Build DP table
        var dp = Array(repeating: Array(repeating: 0, count: n + 1), count: m + 1)
        for i in 1...max(m, 1) where i <= m {
            for j in 1...max(n, 1) where j <= n {
                dp[i][j] = a[i-1] == b[j-1]
                    ? dp[i-1][j-1] + 1
                    : max(dp[i-1][j], dp[i][j-1])
            }
        }

        // Backtrack to produce diff lines
        var result: [Line] = []
        var i = m, j = n
        while i > 0 || j > 0 {
            if i > 0, j > 0, a[i-1] == b[j-1] {
                result.append(.unchanged(a[i-1]))
                i -= 1; j -= 1
            } else if j > 0, (i == 0 || dp[i][j-1] >= dp[i-1][j]) {
                result.append(.added(b[j-1]))
                j -= 1
            } else {
                result.append(.removed(a[i-1]))
                i -= 1
            }
        }
        return result.reversed()
    }
}
