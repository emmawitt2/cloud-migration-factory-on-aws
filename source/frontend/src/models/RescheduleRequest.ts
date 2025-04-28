export type RescheduleRequest = {
  app_id: string;
  reschedule_request_id: string;
  _history: { createdBy: { userRef: string; email: string }; createdTimestamp: string };
};
