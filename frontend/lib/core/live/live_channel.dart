import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../config/api_paths.dart';
import '../network/dio_provider.dart';
import '../network/sse.dart';

/// State of the live SSE stream connection.
enum LiveStreamStatus {
  disconnected,
  connecting,
  connected,
  reconnecting,
}

/// Service managing the live SSE connection to /api/live/stream (§4, §16).
class LiveChannelNotifier extends StateNotifier<LiveStreamStatus> {
  final Dio _dio;
  final String _baseUrl;
  StreamSubscription<SseEvent>? _subscription;
  Timer? _reconnectTimer;
  int _retryBackoffSec = 2;

  final _eventController = StreamController<SseEvent>.broadcast();

  LiveChannelNotifier(this._dio, this._baseUrl) : super(LiveStreamStatus.disconnected) {
    connect();
  }

  /// Broadcast stream of all received SSE events.
  Stream<SseEvent> get events => _eventController.stream;

  /// Connects to the SSE endpoint.
  Future<void> connect() async {
    if (state == LiveStreamStatus.connected || state == LiveStreamStatus.connecting) return;

    state = LiveStreamStatus.connecting;
    _reconnectTimer?.cancel();

    try {
      final response = await _dio.get<ResponseBody>(
        ApiPaths.liveStream,
        options: Options(
          responseType: ResponseType.stream,
          headers: <String, dynamic>{
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache',
          },
        ),
      );

      final stream = response.data?.stream;
      if (stream != null) {
        state = LiveStreamStatus.connected;
        _retryBackoffSec = 2; // reset backoff

        _subscription = stream
            .cast<List<int>>()
            .transform(utf8.decoder)
            .transform(const SseDecoder())
            .listen(
          (event) {
            debugPrint('[LiveChannel SSE] Event: ${event.event} -> ${event.data}');
            _eventController.add(event);
          },
          onError: (Object error) {
            debugPrint('[LiveChannel SSE Error] $error');
            _scheduleReconnect();
          },
          onDone: () {
            debugPrint('[LiveChannel SSE Closed]');
            _scheduleReconnect();
          },
          cancelOnError: true,
        );
      } else {
        _scheduleReconnect();
      }
    } catch (e) {
      debugPrint('[LiveChannel SSE Connect Failed] $e');
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    _subscription?.cancel();
    state = LiveStreamStatus.reconnecting;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(seconds: _retryBackoffSec), () {
      _retryBackoffSec = (_retryBackoffSec * 2).clamp(2, 30);
      connect();
    });
  }

  @override
  void dispose() {
    _reconnectTimer?.cancel();
    _subscription?.cancel();
    _eventController.close();
    super.dispose();
  }
}

/// Provider for the live channel notifier.
final liveChannelProvider = StateNotifierProvider<LiveChannelNotifier, LiveStreamStatus>((ref) {
  final dio = ref.watch(dioProvider);
  final baseUrl = ref.watch(baseUrlProvider);
  return LiveChannelNotifier(dio, baseUrl);
});

/// Typed stream provider for data update events.
final dataUpdatedStreamProvider = StreamProvider<SseEvent>((ref) {
  final channel = ref.watch(liveChannelProvider.notifier);
  return channel.events.where((e) => e.event == 'data.updated' || e.event == 'advisory_update');
});

/// Typed stream provider for alert push events.
final alertPushStreamProvider = StreamProvider<SseEvent>((ref) {
  final channel = ref.watch(liveChannelProvider.notifier);
  return channel.events.where((e) => e.event == 'alert.push' || e.event == 'alert');
});
