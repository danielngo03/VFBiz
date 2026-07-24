<?php

declare(strict_types=1);

namespace Drupal\vfbiz_ai_client\Validation;

/**
 * Keeps CTA paths same-origin and free of credentials or customer identifiers.
 */
final class SafeEntryPath {

  /**
   * Checks whether a path is same-site and contains no sensitive identifiers.
   */
  public static function isValid(string $path): bool {
    if (!str_starts_with($path, '/') || str_starts_with($path, '//')) {
      return FALSE;
    }
    if (parse_url($path, PHP_URL_QUERY) !== NULL || parse_url($path, PHP_URL_FRAGMENT) !== NULL) {
      return FALSE;
    }
    return !preg_match('/(?:token|secret|access[_-]?token|vin)[=\/:]/i', $path);
  }

}
