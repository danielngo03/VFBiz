<?php

declare(strict_types=1);

namespace Drupal\Tests\vfbiz_ai_client\Unit;

use Drupal\Tests\UnitTestCase;
use Drupal\vfbiz_ai_client\Validation\SafeEntryPath;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\Group;

/**
 * Tests safe entry path validation.
 */
#[CoversClass(SafeEntryPath::class)]
#[Group('vfbiz_ai_client')]
final class SafeEntryPathTest extends UnitTestCase {

  /**
   * Tests accepted and rejected path shapes.
   */
  public function testAllowsOnlySafeSameSitePaths(): void {
    self::assertTrue(SafeEntryPath::isValid('/vi/trip-planner'));
    self::assertFalse(SafeEntryPath::isValid('https://example.invalid/account'));
    self::assertFalse(SafeEntryPath::isValid('//example.invalid/account'));
    self::assertFalse(SafeEntryPath::isValid('/account?token=secret'));
    self::assertFalse(SafeEntryPath::isValid('/vehicles/vin/ABC123'));
  }

}
