import 'app_failure.dart';

/// Sealed functional Result type for error handling.
sealed class Result<T> {
  const Result();

  /// Creates a successful result holding [value].
  const factory Result.ok(T value) = Ok<T>;

  /// Creates a failure result holding [failure].
  const factory Result.err(AppFailure failure) = Err<T>;

  /// True if result is successful.
  bool get isOk => this is Ok<T>;

  /// True if result is an error.
  bool get isErr => this is Err<T>;

  /// Unwraps the value or returns null.
  T? get valueOrNull => switch (this) {
        Ok(value: final v) => v,
        Err() => null,
      };

  /// Unwraps the failure or returns null.
  AppFailure? get failureOrNull => switch (this) {
        Ok() => null,
        Err(failure: final f) => f,
      };

  /// Pattern match helper.
  R when<R>({
    required R Function(T value) ok,
    required R Function(AppFailure failure) err,
  }) {
    return switch (this) {
      Ok(value: final v) => ok(v),
      Err(failure: final f) => err(f),
    };
  }

  /// Maps successful value.
  Result<R> map<R>(R Function(T value) transform) {
    return switch (this) {
      Ok(value: final v) => Result.ok(transform(v)),
      Err(failure: final f) => Result.err(f),
    };
  }
}

/// Success container.
final class Ok<T> extends Result<T> {
  final T value;
  const Ok(this.value);

  @override
  bool operator ==(Object other) =>
      identical(this, other) || (other is Ok<T> && other.value == value);

  @override
  int get hashCode => value.hashCode;

  @override
  String toString() => 'Ok($value)';
}

/// Error container.
final class Err<T> extends Result<T> {
  final AppFailure failure;
  const Err(this.failure);

  @override
  bool operator ==(Object other) =>
      identical(this, other) || (other is Err<T> && other.failure == failure);

  @override
  int get hashCode => failure.hashCode;

  @override
  String toString() => 'Err($failure)';
}
