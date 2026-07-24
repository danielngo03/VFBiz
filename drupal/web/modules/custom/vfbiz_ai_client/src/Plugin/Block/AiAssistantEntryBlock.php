<?php

declare(strict_types=1);

namespace Drupal\vfbiz_ai_client\Plugin\Block;

use Drupal\Component\Utility\Html;
use Drupal\Core\Block\Attribute\Block;
use Drupal\Core\Block\BlockBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\StringTranslation\TranslatableMarkup;
use Drupal\vfbiz_ai_client\Validation\SafeEntryPath;

/**
 * Provides an editorially configurable client-only assistant entry.
 */
#[Block(
  id: 'vfbiz_ai_client_entry',
  admin_label: new TranslatableMarkup('VFBiz AI assistant entry'),
  category: new TranslatableMarkup('VFBiz'),
)]
final class AiAssistantEntryBlock extends BlockBase {

  /**
   * {@inheritdoc}
   *
   * @return array<string, mixed>
   *   The default block configuration.
   */
  public function defaultConfiguration(): array {
    return [
      'heading' => '',
      'description' => '',
      'open_label' => '',
      'account_label' => '',
      'account_path' => '/account',
      'trip_label' => '',
      'trip_path' => '/trip-planner',
    ] + parent::defaultConfiguration();
  }

  /**
   * {@inheritdoc}
   *
   * @param array<string, mixed> $form
   *   The block configuration form.
   * @param \Drupal\Core\Form\FormStateInterface $form_state
   *   The current form state.
   *
   * @return array<string, mixed>
   *   The completed block configuration form.
   */
  public function blockForm($form, FormStateInterface $form_state): array {
    $form = parent::blockForm($form, $form_state);
    foreach (['heading', 'description', 'open_label', 'account_label', 'trip_label'] as $key) {
      $form[$key] = [
        '#type' => $key === 'description' ? 'textarea' : 'textfield',
        '#title' => $this->t('@field', ['@field' => str_replace('_', ' ', ucfirst($key))]),
        '#default_value' => $this->configuration[$key],
        '#required' => TRUE,
        '#maxlength' => $key === 'description' ? 300 : 120,
      ];
    }
    foreach (['account_path', 'trip_path'] as $key) {
      $form[$key] = [
        '#type' => 'textfield',
        '#title' => $this->t('@field', ['@field' => str_replace('_', ' ', ucfirst($key))]),
        '#default_value' => $this->configuration[$key],
        '#required' => TRUE,
        '#description' => $this->t('Use a same-site path without a query string, fragment, token, or VIN.'),
      ];
    }
    return $form;
  }

  /**
   * {@inheritdoc}
   *
   * @param array<string, mixed> $form
   *   The block configuration form.
   * @param \Drupal\Core\Form\FormStateInterface $form_state
   *   The current form state.
   */
  public function blockValidate($form, FormStateInterface $form_state): void {
    parent::blockValidate($form, $form_state);
    foreach (['account_path', 'trip_path'] as $key) {
      if (!SafeEntryPath::isValid((string) $form_state->getValue($key))) {
        $form_state->setErrorByName($key, $this->t('Enter a safe same-site path without query parameters or customer identifiers.'));
      }
    }
  }

  /**
   * {@inheritdoc}
   *
   * @param array<string, mixed> $form
   *   The block configuration form.
   * @param \Drupal\Core\Form\FormStateInterface $form_state
   *   The current form state.
   */
  public function blockSubmit($form, FormStateInterface $form_state): void {
    parent::blockSubmit($form, $form_state);
    foreach (['heading', 'description', 'open_label', 'account_label', 'account_path', 'trip_label', 'trip_path'] as $key) {
      $this->configuration[$key] = trim((string) $form_state->getValue($key));
    }
  }

  /**
   * {@inheritdoc}
   *
   * @return array<string, mixed>
   *   A render array for the AI client entry component.
   */
  public function build(): array {
    if (!SafeEntryPath::isValid($this->configuration['account_path']) || !SafeEntryPath::isValid($this->configuration['trip_path'])) {
      return [];
    }
    return [
      '#type' => 'component',
      '#component' => 'vfbiz_ai_client:ai-client-entry',
      '#props' => [
        'heading' => $this->configuration['heading'],
        'description' => $this->configuration['description'],
        'open_label' => $this->configuration['open_label'],
        'account_label' => $this->configuration['account_label'],
        'account_path' => $this->configuration['account_path'],
        'trip_label' => $this->configuration['trip_label'],
        'trip_path' => $this->configuration['trip_path'],
        'status_id' => Html::getUniqueId('vfbiz-ai-entry-status'),
      ],
      '#cache' => ['contexts' => ['languages:language_interface']],
    ];
  }

}
