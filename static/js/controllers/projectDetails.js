define([
    'app',
    'utils/chartHelpers',
    'utils/duration',
    'utils/escapeHtml',
    'directives/radialProgressBar',
    'directives/timeSince',
    'filters/orderByBuild'], function(app, chartHelpers, duration, escapeHtml) {
  app.controller('projectDetailsCtrl', ['$scope', 'initialProject', 'initialBuildList', '$http', '$routeParams', 'stream', function($scope, initialProject, initialBuildList, $http, $routeParams, Stream) {
    'use strict';

    var stream,
        entrypoint = '/api/0/projects/' + $routeParams.project_id + '/builds/',
        chart_options = {
          tooltipFormatter: function(item) {
            var content = ''

            content += '<h5>';
            content += escapeHtml(item.name);
            content += '<br><small>';
            content += escapeHtml(item.parent_revision.sha.substr(0, 12)) + ' &mdash; ' + item.author.name;
            content += '</small>'
            content += '</h5>';
            if (item.status.id == 'finished') {
              content += '<p>Build ' + item.result.name;
              if (item.duration) {
                content += ' in ' + duration(item.duration);
              }
              content += '</p>';
            } else {
              content += '<p>' + item.status.name + '</p>';
            }

            return content;
          }
        };

    function addBuild(data) {
      $scope.$apply(function() {
        var updated = false,
            item_id = data.id,
            attr, result, item;

        if ($scope.builds.length > 0) {
          result = $.grep($scope.builds, function(e){ return e.id == item_id; });
          if (result.length > 0) {
            item = result[0];
            for (attr in data) {
              // ignore dateModified as we're updating this frequently and it causes
              // the dirty checking behavior in angular to respond poorly
              if (item[attr] != data[attr] && attr != 'dateModified') {
                updated = true;
                item[attr] = data[attr];
              }
              if (updated) {
                item.dateModified = data.dateModified;
              }
            }
          }
        }
        if (!updated) {
          $scope.builds.unshift(data);
          $scope.builds = $scope.builds.slice(0, 100);
        }
      });
    }

    $scope.getBuildStatus = function(build) {
      if (build.status.id == 'finished') {
        return build.result.name;
      } else {
        return build.status.name;
      }
    }

    $scope.project = initialProject.data.project;
    $scope.builds = initialBuildList.data.builds;
    $scope.chartData = chartHelpers.getChartData($scope.builds, null, chart_options);

    $scope.$watch("builds", function() {
      $scope.chartData = chartHelpers.getChartData($scope.builds, null, chart_options);
    });

    stream = Stream($scope, entrypoint);
    stream.subscribe('build.update', addBuild);

  }]);
});
