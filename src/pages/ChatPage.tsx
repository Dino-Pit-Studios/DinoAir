import {
  useEffect,
  useRef,
  useState,
  useCallback,
  type KeyboardEvent,
  type ChangeEvent,
} from 'react';

import { LiveRegion } from '../components/accessibility/LiveRegion';
import Button from '../components/common/Button';
import SearchInput from '../components/common/SearchInput';
import Chat from '../components/icons/Chat';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';
import { useAnnouncement } from '../hooks/useAnnouncement';
import { useResponsive } from '../hooks/useResponsive';
import { sendChatMessage, type ChatMessage } from '../lib/api';

type Msg = { role: 'user' | 'assistant'; text: string };

/**
 * ChatPage component renders a chat interface allowing users to send messages to an AI assistant.
 *
 * @returns {JSX.Element} The chat page layout including messages list, input, and send functionality.
 */
export default function ChatPage() {
  const { isMobile } = useResponsive();
  const { announceInfo, announceSuccess, announceStatus, announceError } = useAnnouncement();
  const [messages, setMessages] = useState<Msg[]>([
    { role: 'assistant', text: 'Hi! How can I help you today?' },
  ]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [selectedModel, setSelectedModel] = useState('gpt-4');
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages, typing]);

  /**
   * Sends the user's input message to the AI assistant API and updates the chat log.
   *
   * @returns {Promise<void>} Resolves when the send operation is complete.
   */
  async function send() {
    const trimmed = input.trim();
    if (!trimmed) {
      return;
    }

    const userMessage: Msg = { role: 'user', text: trimmed };
    setMessages(m => [...m, userMessage]);
    setInput('');
    setTyping(true);

    // Announce that message was sent
    announceSuccess('Message sent. Waiting for response.');

    try {
      // Convert messages to API format
      const apiMessages: ChatMessage[] = [...messages, userMessage].map(msg => ({
        role: msg.role,
        content: msg.text,
      }));

      // Send to LM Studio via the API
      const response = await sendChatMessage({
        messages: apiMessages,
        model: selectedModel,
        temperature: 0.7,
        max_tokens: 2000,
        extra_params: {
          router_tag: 'chat',
        },
      });

      if (response.success && response.content) {
        setMessages(m => [...m, { role: 'assistant', text: response.content }]);
        announceInfo('Assistant has responded.');
      } else {
        setMessages(m => [
          ...m,
          { role: 'assistant', text: 'Sorry, I encountered an error processing your request.' },
        ]);
        announceError('Error processing your request.');
      }
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(m => [
        ...m,
        {
          role: 'assistant',
          text: "Sorry, I'm having trouble connecting to the AI service. Please try again.",
        },
      ]);
      announceError('Connection error. Please try again.');
    } finally {
      setTyping(false);
    }
  }

  /**
   * Handles keydown events on the chat input.
   * If 'Enter' is pressed without holding Shift, prevents default behavior and sends the message.
   * @param e - The keyboard event from the input element.
   */
  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const handleModelChange = useCallback(
    (e: ChangeEvent<HTMLSelectElement>) => {
      const newModel = e.target.value;
      setSelectedModel(newModel);
      announceStatus(`Model changed to ${newModel}`);
    },
    [announceStatus]
  );

  // styles are applied inline below; no shared style object needed

  return (
    <PageContainer className='chat-page'>
      <PageHeader
        icon={<Chat width={20} height={20} />}
        title='Chat'
        actions={
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <label htmlFor='model-selector' style={{ fontSize: 14, color: '#cdd6ff' }}>
              Model:
            </label>
            <select
              id='model-selector'
              data-testid='model-selector'
              value={selectedModel}
              onChange={handleModelChange}
              aria-label='Select AI model'
              style={{
                background: '#0f3460',
                border: '1px solid #2a3b7a',
                borderRadius: 6,
                color: '#e6eaff',
                padding: '6px 10px',
                fontSize: 14,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value='gpt-4'>GPT-4</option>
              <option value='gpt-3.5'>GPT-3.5</option>
              <option value='claude'>Claude</option>
              <option value='llama'>Llama</option>
            </select>
          </div>
        }
      />

      <main role='main' aria-label='Chat conversation'>
        <section
          ref={listRef}
          data-testid='chat-messages'
          role='log'
          aria-label='Chat messages'
          aria-live='polite'
          aria-relevant='additions'
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            background: '#0f3460',
            border: '1px solid #2a3b7a',
            borderRadius: 8,
            padding: isMobile ? '8px' : '12px',
            height: isMobile ? '50vh' : '360px',
            minHeight: '300px',
            maxHeight: '600px',
            overflowY: 'auto',
          }}
        >
          {messages.map((m, i) => (
            <div
              key={i}
              role={m.role === 'user' ? 'article' : 'article'}
              aria-label={`${m.role === 'user' ? 'User' : 'Assistant'} message`}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                background: m.role === 'user' ? '#23346e' : '#16213e',
                border: '1px solid #2a3b7a',
                color: '#e6eaff',
                padding: '8px 10px',
                borderRadius: 10,
                maxWidth: isMobile ? '85%' : '70%',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              <span className='sr-only'>
                {m.role === 'user' ? 'You said: ' : 'Assistant said: '}
              </span>
              {m.text}
            </div>
          ))}
          {typing ? (
            <span
              role='status'
              aria-live='polite'
              aria-label='Assistant is typing'
              style={{ color: '#9fb3ff', fontStyle: 'italic', fontSize: 12 }}
            >
              Assistant is typing…
            </span>
          ) : null}
        </section>

        <section
          style={{
            display: 'flex',
            flexDirection: isMobile ? 'column' : 'row',
            gap: 8,
            alignItems: isMobile ? 'stretch' : 'center',
            marginTop: 10,
          }}
          role='form'
          aria-label='Message input form'
        >
          <div style={{ flex: 1 }} data-testid='chat-input-wrapper'>
            <SearchInput
              value={input}
              onChange={setInput}
              placeholder='Type a message…'
              data-testid='chat-input'
              aria-label='Chat message input'
              onKeyDown={onKeyDown}
              role='textbox'
              aria-multiline='false'
            />
          </div>
          <Button
            onClick={send}
            variant='primary'
            data-testid='send-button'
            aria-label='Send message'
            disabled={!input.trim()}
            style={{
              minWidth: isMobile ? '100%' : 'auto',
            }}
          >
            Send
          </Button>
        </section>
      </main>

      {/* Screen reader live region for announcements */}
      <LiveRegion ariaLabel='Chat page announcements' showLatestOnly />
    </PageContainer>
  );
}
