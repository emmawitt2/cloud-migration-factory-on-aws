/*
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import React from "react";
import { ColumnLayout, Container, Header, SpaceBetween, Tabs } from "@cloudscape-design/components";

import Audit from "./ui_attributes/Audit";
import AllViewerAttributes from "./ui_attributes/AllViewerAttributes";
import { ValueWithLabel } from "./ui_attributes/ValueWithLabel";

type RescheduleRequestParams = {
  schema: Record<string, any>;
  handleTabChange: (arg0: string) => void;
  selectedTab: any;
  reschedule_request: {
    reschedule_request_id: string;
  };
  dataAll: any;
};
const RescheduleRequestView = (props: RescheduleRequestParams) => {
  function handleOnTabChange(activeTabId: string) {
    if (props.handleTabChange) {
      props.handleTabChange(activeTabId);
    }
  }

  function selectedTab() {
    if (props.selectedTab) {
      return props.selectedTab;
    } else {
      return null;
    }
  }

  return (
    <Tabs
      activeTabId={selectedTab()}
      onChange={({ detail }) => handleOnTabChange(detail.activeTabId)}
      tabs={[
        {
          label: "Details",
          id: "details",
          content: (
            <Container header={<Header variant="h2">Details</Header>}>
              <ColumnLayout columns={2} variant="text-grid">
                <SpaceBetween size="l">
                  <ValueWithLabel label="Reschedule Request Id">{props.reschedule_request.reschedule_request_id}</ValueWithLabel>
                  <Audit item={props.reschedule_request} expanded={true} />
                </SpaceBetween>
              </ColumnLayout>
            </Container>
          ),
        },
        {
          label: "All attributes",
          id: "attributes",
          content: (
            <Container header={<Header variant="h2">All attributes</Header>}>
              <ColumnLayout columns={2} variant="text-grid">
                <SpaceBetween size="l">
                  <AllViewerAttributes
                    schema={props.schema.reschedule_request}
                    schemas={props.schema}
                    item={props.reschedule_request}
                    dataAll={props.dataAll}
                  />
                  <Audit item={props.reschedule_request} expanded={true} />
                </SpaceBetween>
              </ColumnLayout>
            </Container>
          ),
        },
      ]}
      // variant="container"
    />
  );
};

export default RescheduleRequestView;
