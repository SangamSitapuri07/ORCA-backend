import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';
import 'bootstrap.dart';

/// Application bootstrap entry point (§10).
void main() async {
  final container = await bootstrap();

  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const OrcaApp(),
    ),
  );
}
