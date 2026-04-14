import SwiftUI

/// Main conversation screen. The copy button in the toolbar always targets
/// the most recent assistant response so the user can grab it in one tap.
struct ConversationView: View {

    @StateObject private var viewModel = CloudOutputViewModel()
    @State private var inputText = ""

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                messageList
                inputBar
            }
            .navigationTitle("MirrorMind")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    CopyOutputButton(text: viewModel.latestCloudOutput)
                }
            }
        }
    }

    // MARK: - Sub-views

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(viewModel.messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }

                    if viewModel.isLoading {
                        TypingIndicator()
                            .id("typing")
                    }
                }
                .padding()
            }
            .onChange(of: viewModel.messages.count) {
                scrollToBottom(proxy: proxy)
            }
            .onChange(of: viewModel.isLoading) {
                if viewModel.isLoading { scrollToBottom(proxy: proxy) }
            }
        }
    }

    private var inputBar: some View {
        HStack(spacing: 8) {
            TextField("Message", text: $inputText, axis: .vertical)
                .lineLimit(1...5)
                .textFieldStyle(.roundedBorder)

            Button {
                let text = inputText
                inputText = ""
                Task { await viewModel.send(text) }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title2)
            }
            .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isLoading)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        let id: AnyHashable = viewModel.isLoading
            ? AnyHashable("typing")
            : AnyHashable(viewModel.messages.last?.id ?? UUID())
        withAnimation { proxy.scrollTo(id, anchor: .bottom) }
    }
}

// MARK: - MessageBubble

private struct MessageBubble: View {
    let message: CloudOutputViewModel.Message

    var isAssistant: Bool { message.role == .assistant }

    var body: some View {
        HStack {
            if !isAssistant { Spacer(minLength: 40) }

            Text(message.content)
                .padding(10)
                .background(isAssistant ? Color(.secondarySystemBackground) : Color.accentColor)
                .foregroundStyle(isAssistant ? .primary : .white)
                .clipShape(RoundedRectangle(cornerRadius: 14))

            if isAssistant { Spacer(minLength: 40) }
        }
        .frame(maxWidth: .infinity, alignment: isAssistant ? .leading : .trailing)
    }
}

// MARK: - TypingIndicator

private struct TypingIndicator: View {
    @State private var phase = 0

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .frame(width: 7, height: 7)
                    .scaleEffect(phase == i ? 1.3 : 1)
                    .animation(.easeInOut(duration: 0.4).repeatForever().delay(Double(i) * 0.15), value: phase)
            }
        }
        .padding(10)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .onAppear { phase = 1 }
    }
}

// MARK: - Preview

#Preview {
    ConversationView()
}
