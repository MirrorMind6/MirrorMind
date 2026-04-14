import SwiftUI

/// Shows exactly what changed between two consecutive framework versions.
/// Green lines were added. Red lines were removed. Grey lines stayed the same.
struct DiffView: View {

    let old: FrameworkVersion
    let new: FrameworkVersion

    private var diffLines: [DiffEngine.Line] {
        DiffEngine.diff(old: old.content, new: new.content)
    }

    private var stats: String {
        DiffEngine.stats(old: old.content, new: new.content)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    // Stats header
                    HStack {
                        Image(systemName: "arrow.left.arrow.right.circle.fill")
                            .foregroundStyle(.secondary)
                        Text("\(old.label) → \(new.label)")
                            .fontWeight(.semibold)
                        Spacer()
                        Text(stats)
                            .foregroundStyle(.secondary)
                    }
                    .font(.subheadline)
                    .padding()
                    .background(Color(.secondarySystemBackground))

                    Divider()

                    // Diff lines
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(diffLines.enumerated()), id: \.offset) { _, line in
                            DiffLineView(line: line)
                        }
                    }
                    .font(.system(.footnote, design: .monospaced))
                }
            }
            .navigationTitle("What changed")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

// MARK: - DiffLineView

private struct DiffLineView: View {
    let line: DiffEngine.Line

    private var prefix: String {
        switch line {
        case .added:     return "+"
        case .removed:   return "−"
        case .unchanged: return " "
        }
    }

    private var background: Color {
        switch line {
        case .added:     return Color.green.opacity(0.15)
        case .removed:   return Color.red.opacity(0.15)
        case .unchanged: return .clear
        }
    }

    private var prefixColor: Color {
        switch line {
        case .added:     return .green
        case .removed:   return .red
        case .unchanged: return .secondary
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(prefix)
                .foregroundStyle(prefixColor)
                .frame(width: 12, alignment: .center)

            Text(line.text.isEmpty ? " " : line.text)
                .foregroundStyle(line.text.isEmpty ? .clear : .primary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 3)
        .background(background)
    }
}

// MARK: - Preview

#Preview {
    DiffView(
        old: FrameworkVersion(
            content: "## Framework v1\n\nCore principle: humans and AI collaborate.\nStep 1: Define the problem.\nStep 2: Iterate.",
            versionNumber: 1
        ),
        new: FrameworkVersion(
            content: "## Framework v2\n\nCore principle: humans and AI collaborate iteratively.\nStep 1: Define the problem clearly.\nStep 2: Iterate.\nStep 3: Document each session.",
            versionNumber: 2
        )
    )
}
