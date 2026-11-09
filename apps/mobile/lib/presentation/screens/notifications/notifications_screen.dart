import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/utils/theme_ext.dart';
import '../../../data/mock/mock_notifications.dart';
import '../../../data/models/notification_model.dart';
import 'package:intl/intl.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  late List<AppNotification> _notifications;

  @override
  void initState() {
    super.initState();
    _notifications = List.from(mockNotifications);
  }

  void _markAllRead() {
    setState(() {
      _notifications =
          _notifications.map((n) => n.copyWith(isRead: true)).toList();
    });
  }

  void _markRead(int index) {
    setState(() {
      _notifications[index] = _notifications[index].copyWith(isRead: true);
    });
  }

  int get _unreadCount =>
      _notifications.where((n) => !n.isRead).length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      appBar: AppBar(
        backgroundColor: context.appBg,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Notifications',
              style: TextStyle(
                color: context.textPri,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (_unreadCount > 0)
              Text(
                '$_unreadCount unread',
                style: const TextStyle(
                  color: AppColors.primary,
                  fontSize: 12,
                  fontWeight: FontWeight.w400,
                ),
              ),
          ],
        ),
        actions: [
          if (_unreadCount > 0)
            TextButton(
              onPressed: _markAllRead,
              child: const Text(
                'Mark all read',
                style: TextStyle(color: AppColors.primary, fontSize: 13),
              ),
            ),
        ],
      ),
      body: _notifications.isEmpty
          ? Center(
              child: Text('No notifications',
                  style: TextStyle(color: context.textMut)),
            )
          : ListView.separated(
              padding: const EdgeInsets.all(AppSpacing.screenPadding),
              itemCount: _notifications.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (ctx, i) => GestureDetector(
                onTap: () => _markRead(i),
                child: _NotificationCard(
                  notification: _notifications[i],
                )
                    .animate(delay: Duration(milliseconds: i * 40))
                    .fadeIn(duration: 300.ms)
                    .slideX(begin: 0.1, end: 0, duration: 300.ms),
              ),
            ),
    );
  }
}

class _NotificationCard extends StatelessWidget {
  const _NotificationCard({required this.notification});

  final AppNotification notification;

  (Color, IconData, String) get _typeStyle => switch (notification.type) {
        NotificationType.hypo =>
          (AppColors.danger, Icons.warning_rounded, 'Low Alert'),
        NotificationType.hyper =>
          (AppColors.warning, Icons.arrow_upward_rounded, 'High Alert'),
        NotificationType.aiRecommendation =>
          (AppColors.primary, Icons.auto_awesome_rounded, 'AI Insight'),
        NotificationType.safetyWarning =>
          (AppColors.accentAmber, Icons.security_rounded, 'Safety'),
        NotificationType.reminder =>
          (AppColors.accentCyan, Icons.notifications_rounded, 'Reminder'),
        NotificationType.info =>
          (AppColors.accentGreen, Icons.info_rounded, 'Info'),
      };

  @override
  Widget build(BuildContext context) {
    final (color, icon, typeLabel) = _typeStyle;
    final isUnread = !notification.isRead;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: isUnread ? color.withValues(alpha: 0.05) : context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(
          color: isUnread ? color.withValues(alpha: 0.2) : context.borderC,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Icon
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: color, size: 20),
          ),
          const SizedBox(width: 12),

          // Content
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      typeLabel,
                      style: TextStyle(
                        color: color,
                        fontSize: 9,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  const Spacer(),
                  Text(
                    _formatTime(notification.timestamp),
                    style: TextStyle(
                      color: context.textMut,
                      fontSize: 10,
                    ),
                  ),
                  if (isUnread) ...[
                    const SizedBox(width: 6),
                    Container(
                      width: 7,
                      height: 7,
                      decoration: BoxDecoration(
                        color: color,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ],
                ]),
                const SizedBox(height: 6),
                Text(
                  notification.title,
                  style: TextStyle(
                    color: isUnread ? context.textPri : context.textSec,
                    fontWeight:
                        isUnread ? FontWeight.w600 : FontWeight.w400,
                    fontSize: 13,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  notification.body,
                  style: TextStyle(
                    color: context.textSec,
                    fontSize: 12,
                    height: 1.4,
                  ),
                ),
                if (notification.actionLabel != null) ...[
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 5),
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                          color: color.withValues(alpha: 0.3)),
                    ),
                    child: Text(
                      notification.actionLabel!,
                      style: TextStyle(
                        color: color,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatTime(DateTime time) {
    final now = DateTime.now();
    final diff = now.difference(time);
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return DateFormat('MMM d').format(time);
  }
}
