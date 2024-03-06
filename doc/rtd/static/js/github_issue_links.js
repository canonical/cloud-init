window.onload = function () {
  const link = document.createElement("a");
  link.classList.add("muted-link");
  link.classList.add("github-issue-link");
  link.text = "Give feedback";
  link.href = (
    "https://github.com/canonical/cloud-init/issues/new?"
    + "assignees=&labels=documentation%2C+new&projects=&template=documentation.md&title=%5Bdocs%5D%3A+"
    + "&body=%23 Documentation request"
    + "%0A%0A%0A%0A%0A"
    + "---"
    + "%0A"
    + `*Reported+from%3A+${location.href}*`
  );
  link.target = "_blank";

  const div = document.createElement("div");
  div.classList.add("github-issue-link-container");
  div.append(link)

  const container = document.querySelector(".article-container > .content-icon-container");
  container.prepend(div);
};
