((Drupal, once) => {
  Drupal.behaviors.vfbizAiClientEntry = {
    attach(context) {
      once('vfbiz-ai-client-entry', '[data-vfbiz-ai-entry]', context).forEach((entry) => {
        const trigger = entry.querySelector('[data-vfbiz-ai-open]');
        const status = entry.querySelector('[data-vfbiz-ai-status]');
        if (!(trigger instanceof HTMLButtonElement) || !(status instanceof HTMLElement)) return;

        trigger.addEventListener('click', () => {
          trigger.setAttribute('aria-busy', 'true');
          status.textContent = Drupal.t('Opening the assistant…');
          entry.dispatchEvent(new CustomEvent('vfbiz:ai-client:open', {
            bubbles: true,
            detail: Object.freeze({profile: 'public_customer', source: 'drupal'}),
          }));
        });

        entry.addEventListener('vfbiz:ai-client:state', (event) => {
          const state = event instanceof CustomEvent ? event.detail?.state : undefined;
          const messages = {
            ready: Drupal.t('Assistant is ready.'),
            unavailable: Drupal.t('Assistant is temporarily unavailable. Please use the account or support channel.'),
          };
          if (!Object.hasOwn(messages, state)) return;
          status.textContent = messages[state];
          trigger.removeAttribute('aria-busy');
          trigger.setAttribute('aria-expanded', state === 'ready' ? 'true' : 'false');
          trigger.disabled = false;
        });
      });
    },
  };
})(Drupal, once);
