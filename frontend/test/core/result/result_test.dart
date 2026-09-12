import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/result/app_failure.dart';
import 'package:orca_app/core/result/result.dart';

void main() {
  group('Result<T> Functional Tests', () {
    test('Ok contains value and isOk is true', () {
      const result = Result.ok(42);
      expect(result.isOk, isTrue);
      expect(result.isErr, isFalse);
      expect(result.valueOrNull, equals(42));
      expect(result.failureOrNull, isNull);
    });

    test('Err contains failure and isErr is true', () {
      const result = Result<int>.err(AppFailure.offline());
      expect(result.isOk, isFalse);
      expect(result.isErr, isTrue);
      expect(result.valueOrNull, isNull);
      expect(result.failureOrNull, isA<OfflineFailure>());
    });

    test('Pattern match when executes proper callback', () {
      const okResult = Result.ok('success');
      final okMapped = okResult.when(
        ok: (v) => 'VALUE: $v',
        err: (f) => 'ERROR: $f',
      );
      expect(okMapped, equals('VALUE: success'));

      const errResult = Result<String>.err(AppFailure.serverDown('500'));
      final errMapped = errResult.when(
        ok: (v) => 'VALUE: $v',
        err: (f) => 'ERROR: ${f.message}',
      );
      expect(errMapped, contains('500'));
    });
  });
}
